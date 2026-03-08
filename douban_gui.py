#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆瓣爬虫图形界面
- 先登录，等待用户确认后再开始爬取
- 自动处理验证码
- 保存到 MediaCrawler 数据目录
"""

import asyncio
import contextlib
import io
import json
import queue
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from playwright.async_api import async_playwright, Browser, Page

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ==================== 配置 ====================
DATA_DIR = Path("../MediaCrawler/data/douban/json")
DEFAULT_KEYWORD = "爱你老己"
DEFAULT_MAX_POSTS = 500
DEFAULT_MAX_COMMENTS = 15
REQUEST_DELAY_MIN = 4
REQUEST_DELAY_MAX = 8

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# 日志文件
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


class QueueWriter(io.TextIOBase):
    """将 print 输出重定向到线程安全队列 + 保存到文件"""

    def __init__(self, output_queue: queue.Queue, log_file: Path = None):
        self.output_queue = output_queue
        self.log_file = log_file
        self.log_handle = None
        if log_file:
            self.log_handle = open(log_file, "w", encoding="utf-8")

    def write(self, s: str) -> int:
        if s:
            self.output_queue.put(s)
            if self.log_handle:
                self.log_handle.write(s)
                self.log_handle.flush()
        return len(s)

    def flush(self):
        if self.log_handle:
            self.log_handle.flush()
        return None

    def close(self):
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None


class DoubanCrawler:
    """豆瓣爬虫核心类"""

    def __init__(self, delay_min: float = REQUEST_DELAY_MIN, delay_max: float = REQUEST_DELAY_MAX):
        self.browser: Browser = None
        self.page: Page = None
        self.context = None
        self.playwright = None

        self.posts_data = []
        self.comments_data = []
        self.total_posts = 0
        self.total_comments = 0
        self.crawled_topic_ids = set()  # Track crawled topics for resume

        self.paused = False
        self.should_stop = False
        self.logged_in = False

        # 可配置的延迟时间
        self.delay_min = delay_min
        self.delay_max = delay_max

        # 用于等待用户确认继续
        self.wait_for_continue = asyncio.Event()
        self.continue_requested = False

        # 调试目录（由 GUI 设置）
        self.debug_dir = DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def set_paused(self, paused: bool):
        self.paused = paused
        if paused:
            print("⏸ 已暂停")
        else:
            print("▶ 已恢复")

    def stop(self):
        self.should_stop = True
        # 如果正在等待继续，也停止
        if self.wait_for_continue:
            self.wait_for_continue.set()
        print("⏹ 正在停止...")

    def request_continue(self):
        """用户点击继续"""
        self.continue_requested = True
        self.wait_for_continue.set()

    async def init_browser(self):
        """初始化浏览器"""
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "请先安装 playwright: pip install playwright && python -m playwright install chromium"
            )

        print("🌐 启动浏览器...")
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=False, args=["--disable-blink-features=AutomationControlled"]
        )

        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=random.choice(USER_AGENTS),
        )

        self.page = await self.context.new_page()
        # Anti-detection: disable webdriver flag
        await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
        print("✅ 浏览器已启动")

    async def wait_for_login(self) -> bool:
        """等待用户登录（不自动检测，用户手动确认）"""
        print("\n" + "=" * 50)
        print("🔐 登录步骤")
        print("=" * 50)
        print("📱 请在浏览器窗口中完成登录：")
        print("   1. 使用扫码或账号密码登录豆瓣")
        print("   2. 登录成功后，点击 GUI 界面的「继续爬取」按钮")
        print("=" * 50 + "\n")

        # 访问豆瓣首页
        await self.page.goto("https://www.douban.com", wait_until="load", timeout=60000)

        # 等待用户点击"继续"按钮（最多10分钟）
        self.wait_for_continue.clear()
        self.continue_requested = False

        print("⏳ 等待登录...（登录后请点击「继续爬取」）\n")

        # 定期提示
        wait_seconds = 0
        while (
            not self.continue_requested and not self.should_stop and wait_seconds < 600
        ):
            await asyncio.sleep(1)
            wait_seconds += 1

            if wait_seconds % 30 == 0:
                print(f"  ⏳ 已等待 {wait_seconds} 秒...（登录后请点击「继续爬取」）")

        if self.should_stop:
            print("⚠️ 已取消")
            return False

        if not self.continue_requested:
            print("⚠️ 等待超时")
            return False

        print("\n✅ 收到继续信号，开始爬取！\n")
        self.logged_in = True
        await asyncio.sleep(1)
        return True

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _random_delay(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        print(f"  ⏳ 等待 {delay:.1f} 秒...")
        await asyncio.sleep(delay)

    async def _wait_if_paused(self):
        while self.paused and not self.should_stop:
            await asyncio.sleep(0.5)

    async def _check_captcha(self) -> bool:
        """检查并等待验证码"""
        content = await self.page.content()
        
        # 更精确的验证码检测：检查特定元素或页面结构
        captcha_selectors = [
            "iframe[src*='captcha']",
            ".captcha",
            "#captcha",
            "[class*='captcha']",
            ".verify-wrap",
            "#verify-page",
        ]
        
        # 只有当页面明确是验证码页面时才触发
        is_captcha_page = False
        for selector in captcha_selectors:
            elem = await self.page.query_selector(selector)
            if elem:
                is_captcha_page = True
                break
        
        # 备用：检查页面标题或URL
        if not is_captcha_page:
            page_url = self.page.url
            if "captcha" in page_url.lower() or "verify" in page_url.lower():
                is_captcha_page = True
        
        if is_captcha_page:
            print("\n  🔐 检测到验证码！")
            print("  📌 请在浏览器窗口中完成验证码...")
            print("  ⏳ 等待中...\n")

            for i in range(300):
                if self.should_stop:
                    return False
                await asyncio.sleep(1)
                
                # 检查验证码是否消失
                current_url = self.page.url
                still_captcha = "captcha" in current_url.lower() or "verify" in current_url.lower()
                
                if not still_captcha:
                    for selector in captcha_selectors:
                        elem = await self.page.query_selector(selector)
                        if elem:
                            still_captcha = True
                            break
                
                if not still_captcha:
                    print("  ✅ 验证码已完成！\n")
                    await asyncio.sleep(2)
                    return True
                    
                if i > 0 and i % 30 == 0:
                    print(f"  ⏳ 已等待 {i} 秒...")

            print("  ⚠️ 验证码等待超时")
            return False

        return True

    async def start_crawl(self, keyword: str, max_posts: int, max_comments: int,
                          skip_collect: bool = False):
        """开始爬取（在登录后调用）"""
        self.should_stop = False
        self.paused = False

        await self.init_browser()

        try:
            # 1. 等待登录
            if not await self.wait_for_login():
                return

            # 2. 加载已爬取的数据（用于断点续爬）
            self._load_existing_data()

            # 3. 两阶段爬取
            print(f"\n🔍 搜索关键词: {keyword}")
            print(f"⏱️ 延迟设置: {self.delay_min:.1f}-{self.delay_max:.1f} 秒")
            if self.total_posts > 0:
                print(f"🔄 断点续爬: 已有 {self.total_posts} 个帖子, {self.total_comments} 条评论")
            if skip_collect:
                print(f"📂 将尝试使用已缓存的帖子链接")
            await self._parse_search_results(keyword, max_posts, max_comments, skip_collect)

        finally:
            await self.close()

    def _load_existing_data(self):
        """加载已存在的数据文件，用于恢复爬取"""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        contents_file = DATA_DIR / f"search_contents_{timestamp}.json"
        comments_file = DATA_DIR / f"search_comments_{timestamp}.json"
        
        if contents_file.exists():
            try:
                with open(contents_file, "r", encoding="utf-8") as f:
                    existing_posts = json.load(f)
                    self.posts_data = existing_posts
                    self.total_posts = len(existing_posts)
                    for post in existing_posts:
                        if post.get("note_id"):
                            self.crawled_topic_ids.add(post["note_id"])
                print(f"📂 已加载 {len(existing_posts)} 个已爬取的帖子")
            except Exception as e:
                print(f"⚠️ 加载已有数据失败: {e}")
        
        if comments_file.exists():
            try:
                with open(comments_file, "r", encoding="utf-8") as f:
                    existing_comments = json.load(f)
                    self.comments_data = existing_comments
                    self.total_comments = len(existing_comments)
                print(f"📂 已加载 {len(existing_comments)} 条已爬取的评论")
            except Exception as e:
                print(f"⚠️ 加载已有评论失败: {e}")

    async def _parse_search_results(
        self, keyword: str, max_posts: int, max_comments: int,
        skip_collect: bool = False
    ):
        """两阶段爬取：先收集帖子URL，再逐个爬取详情"""

        # URL 缓存文件
        url_cache_file = DATA_DIR / f"url_cache_{keyword}.json"

        # ============================================================
        # 阶段一：收集帖子 URL（不进入帖子详情页）
        # ============================================================
        topic_list = []  # [(url, title), ...]

        # 如果选择跳过收集，尝试从缓存加载
        if skip_collect and url_cache_file.exists():
            try:
                with open(url_cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    topic_list = [(item["url"], item["title"]) for item in cached]
                print(f"\n📂 从缓存加载 {len(topic_list)} 个帖子链接")
                print(f"   缓存文件: {url_cache_file}")
            except Exception as e:
                print(f"⚠️ 加载缓存失败: {e}，将重新收集")
                topic_list = []

        if not topic_list:
            print(f"\n{'=' * 50}")
            print(f"📋 阶段一：收集帖子链接")
            print(f"{'=' * 50}")

            start = 0
            page_size = 20  # 豆瓣小组搜索每页 20 条

            while len(topic_list) < max_posts and not self.should_stop:
                await self._wait_if_paused()
                if self.should_stop:
                    break

                # 构造翻页 URL
                search_url = f"https://www.douban.com/group/search?cat=1013&q={quote(keyword)}&start={start}"
                print(f"\n🌐 访问搜索第 {start // page_size + 1} 页: {search_url}")

                try:
                    await self.page.goto(search_url, wait_until="load", timeout=60000)
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"  ⚠️ 访问搜索页失败: {e}")
                    break

                await asyncio.sleep(2)

                if not await self._check_captcha():
                    break

                # 调试：保存第一页 HTML
                if start == 0:
                    try:
                        content = await self.page.content()
                        debug_file = self.debug_dir / "debug_search_page.html"
                        debug_file.write_text(content, encoding="utf-8")
                        print(f"  📄 搜索页已保存到: {debug_file}")
                    except Exception:
                        pass

                # 解析帖子链接
                content = await self.page.content()
                soup = BeautifulSoup(content, "lxml")

                # 小组搜索结果中的帖子链接
                new_topics_on_page = 0
                all_links = soup.find_all("a", href=True)

                for link in all_links:
                    href = link.get("href", "")
                    match = re.search(r"douban\.com/group/topic/(\d+)", href)
                    if match:
                        topic_id = match.group(1)
                        if topic_id in self.crawled_topic_ids:
                            continue  # 已爬取过，跳过

                        full_url = f"https://www.douban.com/group/topic/{topic_id}/"
                        # 尝试获取标题
                        title = link.get("title", "") or link.get_text(strip=True) or "无标题"
                        # 清理标题
                        if len(title) > 100:
                            title = title[:100]

                        # 避免重复添加同一个 topic
                        if topic_id not in {re.search(r'/topic/(\d+)/', u).group(1) for u, _ in topic_list if re.search(r'/topic/(\d+)/', u)}:
                            topic_list.append((full_url, title))
                            new_topics_on_page += 1

                        if len(topic_list) >= max_posts:
                            break

                print(f"  📄 本页新增 {new_topics_on_page} 个帖子链接 (累计: {len(topic_list)})")

                if new_topics_on_page == 0:
                    print(f"  ✅ 没有更多搜索结果")
                    break

                # 翻页
                start += page_size
                await self._random_delay()

            print(f"\n📋 共收集 {len(topic_list)} 个帖子链接")

            # 保存 URL 缓存
            if topic_list:
                try:
                    cache_data = [{"url": url, "title": title} for url, title in topic_list]
                    with open(url_cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                    print(f"💾 帖子链接已缓存到: {url_cache_file}")
                    print(f"   下次可勾选「使用已缓存的帖子链接」跳过收集")
                except Exception as e:
                    print(f"⚠️ 保存缓存失败: {e}")

        if not topic_list:
            print("⚠️ 未找到任何帖子")
            return

        # ============================================================
        # 阶段二：逐个爬取帖子详情
        # ============================================================
        print(f"\n{'=' * 50}")
        print(f"📝 阶段二：逐个爬取帖子详情")
        print(f"{'=' * 50}")

        crawled_count = 0
        skipped_count = 0
        for idx, (post_url, title) in enumerate(topic_list):
            if self.should_stop:
                break

            await self._wait_if_paused()
            if self.should_stop:
                break

            # 检查是否已爬取（断点续爬）
            match = re.search(r'/topic/(\d+)/', post_url)
            if match and match.group(1) in self.crawled_topic_ids:
                skipped_count += 1
                continue

            if skipped_count > 0 and crawled_count == 0:
                print(f"\n  ⏭️ 已跳过 {skipped_count} 个已爬取的帖子（断点续爬）")

            print(f"\n  📝 [{idx + 1}/{len(topic_list)}] {title[:40]}...")
            print(f"     🔗 {post_url}")

            success = await self._crawl_topic(post_url, title, keyword, max_comments)

            if success:
                crawled_count += 1
                # 记录已爬取的 topic_id
                if match:
                    self.crawled_topic_ids.add(match.group(1))

                comment_count = len(
                    [c for c in self.comments_data if c.get("note_id") == self.posts_data[-1].get("note_id")]
                )
                print(f"    ✅ 成功 (评论: {comment_count}) [本次新增: {crawled_count}, 总计: {len(self.posts_data)}]")

                # 增量保存
                self.save_data()
            else:
                print(f"    ❌ 失败")

            await self._random_delay()

        # Final save
        self.save_data()

        print(f"\n{'=' * 50}")
        print(f"📊 爬取完成: 本次新增 {crawled_count} 个, 跳过 {skipped_count} 个, 总计 {len(self.posts_data)} 个帖子")
        print(f"{'=' * 50}")

    async def _crawl_topic(
        self, url: str, title: str, keyword: str, max_comments: int
    ) -> bool:
        """爬取单个帖子"""
        try:
            await self.page.goto(url, wait_until="load", timeout=60000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            if not await self._check_captcha():
                return False
            
            # Wait for comments section to load
            try:
                await self.page.wait_for_selector("ul#comments", timeout=10000)
            except Exception:
                print("    ⚠️ 评论区未加载，继续尝试解析")
            
            await asyncio.sleep(1)
            content = await self.page.content()
            soup = BeautifulSoup(content, "lxml")

            topic_doc = soup.find("div", class_="topic-doc")
            if not topic_doc:
                return False

            author = ""
            from_elem = topic_doc.find("span", class_="from")
            if from_elem:
                author_link = from_elem.find("a")
                author = author_link.get_text(strip=True) if author_link else ""

            post_time = ""
            time_elem = topic_doc.find("span", class_="create-time")
            if time_elem:
                post_time = time_elem.get_text(strip=True)

            post_content = ""
            content_div = soup.find("div", id="link-report")
            if content_div:
                for tag in content_div.find_all(["script", "style"]):
                    tag.decompose()
                post_content = content_div.get_text(strip=True)

            topic_id = ""
            match = re.search(r"/topic/(\d+)/", url)
            if match:
                topic_id = match.group(1)

            like_count = "0"
            react_elem = soup.find("div", class_="action-react")
            if react_elem:
                react_num = react_elem.find("span", class_="react-num")
                like_count = react_num.get_text(strip=True) if react_num else "0"

            post_data = {
                "note_id": topic_id,
                "type": "search",
                "title": title,
                "desc": post_content[:500] if post_content else "",
                "content": post_content,
                "time": self._parse_time(post_time),
                "time_str": post_time,
                "user_id": "",
                "nickname": author,
                "avatar": "",
                "liked_count": like_count,
                "comment_count": "0",
                "note_url": url,
                "source_keyword": keyword,
                "platform": "douban",
            }

            self.posts_data.append(post_data)
            self.total_posts += 1

            # Parse comments with pagination support
            comments = await self._parse_comments_with_pagination(topic_id, max_comments)
            self.comments_data.extend(comments)
            self.total_comments += len(comments)

            return True

        except Exception as e:
            print(f"    ⚠️ 爬取失败: {e}")
            return False

    async def _parse_comments_with_pagination(self, topic_id: str, max_comments: int) -> list:
        """解析评论（支持翻页）"""
        all_comments = []
        page_num = 1
        
        while len(all_comments) < max_comments and not self.should_stop:
            await self._wait_if_paused()
            
            content = await self.page.content()
            soup = BeautifulSoup(content, "lxml")
            
            comments = self._parse_comments_from_soup(soup, topic_id)
            if not comments:
                break
            
            all_comments.extend(comments)
            print(f"      📝 已解析 {len(all_comments)} 条评论")
            
            if len(all_comments) >= max_comments:
                break
            
            # Check for next page
            paginator = soup.find("div", class_="paginator")
            if not paginator:
                break
            
            next_link = paginator.find("span", class_="next")
            if not next_link or not next_link.find("a"):
                break
            
            # Click next page
            try:
                next_btn = await self.page.query_selector("div.paginator span.next a")
                if next_btn:
                    print(f"      ➡️ 加载评论第 {page_num + 1} 页...")
                    await next_btn.click()
                    await asyncio.sleep(2)
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    page_num += 1
                else:
                    break
            except Exception as e:
                print(f"      ⚠️ 无法加载下一页评论: {e}")
                break
        
        return all_comments[:max_comments]
    
    def _parse_comments_from_soup(self, soup, topic_id: str) -> list:
        """从 BeautifulSoup 对象解析评论"""
        comments = []

        comments_list = soup.find("ul", id="comments")
        if not comments_list:
            return comments

        comment_items = comments_list.find_all("li", recursive=False)

        for item in comment_items:
            try:
                comment = {
                    "comment_id": item.get("data-cid", ""),
                    "note_id": topic_id,
                    "platform": "douban",
                }

                reply_doc = item.find("div", class_="reply-doc")
                if reply_doc:
                    author_elem = (
                        reply_doc.find("h4").find("a") if reply_doc.find("h4") else None
                    )
                    comment["nickname"] = (
                        author_elem.get_text(strip=True) if author_elem else ""
                    )

                    time_elem = reply_doc.find("span", class_="pubtime")
                    time_str = time_elem.get_text(strip=True) if time_elem else ""
                    comment["create_time"] = self._parse_time(time_str)
                    comment["time_str"] = time_str

                    # 解析评论内容（豆瓣评论结构：div.reply-content > div.markdown > p）
                    content_text = ""
                    # 方法1：div.reply-content（新版豆瓣）
                    content_div = reply_doc.find("div", class_="reply-content")
                    if content_div:
                        # 排除引用内容（reply-quote）
                        quote = content_div.find("div", class_="reply-quote")
                        if quote:
                            quote.decompose()
                        # 尝试从 div.markdown > p 获取
                        markdown_div = content_div.find("div", class_="markdown")
                        if markdown_div:
                            content_text = markdown_div.get_text(strip=True)
                        else:
                            content_text = content_div.get_text(strip=True)
                    # 方法2：p.reply-content（旧版豆瓣兼容）
                    if not content_text:
                        content_p = reply_doc.find("p", class_="reply-content")
                        if content_p:
                            span_elem = content_p.find("span")
                            if span_elem:
                                content_text = span_elem.get_text(strip=True)
                            else:
                                content_text = content_p.get_text(strip=True)
                    comment["content"] = content_text

                    comment["user_id"] = ""
                    comment["avatar"] = ""
                    comment["sub_comment_count"] = 0
                    comment["pictures"] = ""
                    comment["like_count"] = "0"
                    comment["ip_location"] = ""
                    comment["parent_comment_id"] = ""

                comments.append(comment)

            except Exception:
                continue

        return comments

    def _parse_time(self, time_str: str) -> int:
        """解析时间为时间戳"""
        if not time_str:
            return 0

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%m-%d %H:%M",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(time_str.strip(), fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue

        return 0

    def save_data(self):
        """保存数据"""
        if not self.posts_data:
            print("⚠️ 没有数据需要保存")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")

        contents_file = DATA_DIR / f"search_contents_{timestamp}.json"
        with open(contents_file, "w", encoding="utf-8") as f:
            json.dump(self.posts_data, f, ensure_ascii=False, indent=2)

        comments_file = DATA_DIR / f"search_comments_{timestamp}.json"
        with open(comments_file, "w", encoding="utf-8") as f:
            json.dump(self.comments_data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 数据已保存:")
        print(f"   - 帖子: {contents_file}")
        print(f"   - 评论: {comments_file}")


class DoubanGUI(tk.Tk):
    """豆瓣爬虫 GUI"""

    def __init__(self):
        super().__init__()
        self.title("豆瓣爬虫 - 关键词搜索")
        self.geometry("900x700")
        self.minsize(800, 600)

        self.log_queue: queue.Queue = queue.Queue()
        self.task_running = False
        self.task_paused = False
        self.waiting_for_login = False  # 是否在等待登录
        self.active_crawler: DoubanCrawler | None = None
        self.active_crawler_lock = threading.Lock()

        self.keyword_var = tk.StringVar(value=DEFAULT_KEYWORD)
        self.max_posts_var = tk.StringVar(value=str(DEFAULT_MAX_POSTS))
        self.max_comments_var = tk.StringVar(value=str(DEFAULT_MAX_COMMENTS))
        self.delay_min_var = tk.StringVar(value=str(REQUEST_DELAY_MIN))
        self.delay_max_var = tk.StringVar(value=str(REQUEST_DELAY_MAX))
        self.use_cached_urls_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.after(100, self._drain_log_queue)

        self._append_log(
            "欢迎使用豆瓣爬虫！\n"
            "使用方法：\n"
            "1. 输入搜索关键词\n"
            "2. 设置爬取数量\n"
            "3. 点击「开始爬取」\n"
            "4. 浏览器会自动打开豆瓣首页\n"
            "5. 在浏览器中登录豆瓣\n"
            "6. 登录完成后，点击「继续爬取」按钮\n\n"
        )

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # === 设置区域 ===
        settings_card = ttk.LabelFrame(root, text="爬取设置", padding=12)
        settings_card.grid(row=0, column=0, sticky="nsew")
        settings_card.columnconfigure(1, weight=1)

        ttk.Label(settings_card, text="搜索关键词：").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings_card, textvariable=self.keyword_var, width=40).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        ttk.Label(settings_card, text="最大帖子数：").grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Entry(settings_card, textvariable=self.max_posts_var, width=10).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(10, 0)
        )

        ttk.Label(settings_card, text="每帖评论数：").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Entry(settings_card, textvariable=self.max_comments_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(10, 0)
        )

        # 延迟设置行
        delay_frame = ttk.Frame(settings_card)
        delay_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(delay_frame, text="动作间隔(秒)：").pack(side=tk.LEFT)
        ttk.Entry(delay_frame, textvariable=self.delay_min_var, width=5).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(delay_frame, text="~").pack(side=tk.LEFT, padx=4)
        ttk.Entry(delay_frame, textvariable=self.delay_max_var, width=5).pack(side=tk.LEFT)
        ttk.Label(delay_frame, text="（越小越快，但容易触发验证码）").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Checkbutton(
            settings_card,
            text="使用已缓存的帖子链接（跳过搜索收集阶段）",
            variable=self.use_cached_urls_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Label(
            settings_card,
            text="💡 断点续爬：勾选缓存+已有数据会自动跳过已爬取的帖子",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # === 操作区域 ===
        actions_card = ttk.LabelFrame(root, text="操作", padding=12)
        actions_card.grid(row=1, column=0, sticky="ew", pady=(10, 10))

        self.start_btn = ttk.Button(
            actions_card, text="▶ 开始爬取", command=self.on_start
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 8))

        # 继续按钮（初始禁用）
        self.continue_btn = ttk.Button(
            actions_card, text="▶ 继续爬取", command=self.on_continue, state=tk.DISABLED
        )
        self.continue_btn.grid(row=0, column=1, padx=8)

        self.pause_btn = ttk.Button(
            actions_card, text="⏸ 暂停", command=self.on_pause, state=tk.DISABLED
        )
        self.pause_btn.grid(row=0, column=2, padx=8)

        self.stop_btn = ttk.Button(
            actions_card, text="⏹ 停止", command=self.on_stop, state=tk.DISABLED
        )
        self.stop_btn.grid(row=0, column=3, padx=8)

        self.clear_btn = ttk.Button(
            actions_card, text="清空日志", command=self._clear_log
        )
        self.clear_btn.grid(row=0, column=4, padx=8)

        self.state_label = ttk.Label(actions_card, text="状态：空闲")
        self.state_label.grid(row=0, column=5, padx=(20, 0))

        # === 日志区域 ===
        log_card = ttk.LabelFrame(root, text="运行日志", padding=12)
        log_card.grid(row=2, column=0, sticky="nsew")
        log_card.rowconfigure(0, weight=1)
        log_card.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_card, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            log_card, orient=tk.VERTICAL, command=self.log_text.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=y_scroll.set)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _append_log(self, text: str):
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def _set_state(self, state: str):
        """设置状态"""
        self.state_label.configure(text=f"状态：{state}")

    def _set_running(self, running: bool, waiting_login: bool = False):
        self.task_running = running
        self.waiting_for_login = waiting_login

        if running:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.clear_btn.configure(state=tk.DISABLED)

            if waiting_login:
                # 等待登录状态：启用继续按钮
                self.continue_btn.configure(state=tk.NORMAL)
                self.pause_btn.configure(state=tk.DISABLED)
                self._set_state("等待登录")
            else:
                # 正在爬取状态
                self.continue_btn.configure(state=tk.DISABLED)
                self.pause_btn.configure(state=tk.NORMAL)
                self._set_state("运行中")
        else:
            self.task_paused = False
            self.start_btn.configure(state=tk.NORMAL)
            self.continue_btn.configure(state=tk.DISABLED)
            self.pause_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.DISABLED)
            self.clear_btn.configure(state=tk.NORMAL)
            self._set_state("空闲")
            self._set_active_crawler(None)

    def _set_active_crawler(self, crawler: DoubanCrawler | None):
        with self.active_crawler_lock:
            self.active_crawler = crawler

    def _get_active_crawler(self) -> DoubanCrawler | None:
        with self.active_crawler_lock:
            return self.active_crawler

    def _drain_log_queue(self):
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__TASK_DONE__":
                self._set_running(False)
            elif item == "__WAITING_LOGIN__":
                self._set_running(True, waiting_login=True)
            elif item == "__LOGIN_DONE__":
                self._set_running(True, waiting_login=False)
            else:
                self._append_log(item if isinstance(item, str) else str(item))

        self.after(100, self._drain_log_queue)

    def on_start(self):
        """开始爬取"""
        if self.task_running:
            messagebox.showwarning("提示", "已有任务在运行")
            return

        try:
            keyword = self.keyword_var.get().strip()
            if not keyword:
                raise ValueError("请输入搜索关键词")

            max_posts = int(self.max_posts_var.get().strip())
            if max_posts <= 0:
                raise ValueError("帖子数必须大于 0")

            max_comments = int(self.max_comments_var.get().strip())
            if max_comments <= 0:
                raise ValueError("评论数必须大于 0")

            delay_min = float(self.delay_min_var.get().strip())
            delay_max = float(self.delay_max_var.get().strip())
            if delay_min < 0 or delay_max < 0:
                raise ValueError("延迟时间不能为负数")
            if delay_min > delay_max:
                delay_min, delay_max = delay_max, delay_min

        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return

        skip_collect = self.use_cached_urls_var.get()

        self._append_log(f"\n{'=' * 50}\n")
        self._append_log(f"🚀 开始\n")
        self._append_log(f"   关键词: {keyword}\n")
        self._append_log(f"   最大帖子: {max_posts}\n")
        self._append_log(f"   每帖评论: {max_comments}\n")
        self._append_log(f"   动作间隔: {delay_min:.1f}-{delay_max:.1f} 秒\n")
        if skip_collect:
            self._append_log(f"   📂 使用已缓存的帖子链接\n")
        self._append_log(f"{'=' * 50}\n")

        def worker():
            # 创建日志文件
            log_file = LOG_DIR / f"crawler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            writer = QueueWriter(self.log_queue, log_file)
            try:
                with contextlib.redirect_stdout(writer):
                    crawler = DoubanCrawler(delay_min=delay_min, delay_max=delay_max)
                    self._set_active_crawler(crawler)

                    # 先通知进入等待登录状态
                    self.log_queue.put("__WAITING_LOGIN__")

                    # 设置调试目录
                    crawler.debug_dir = LOG_DIR
                    print(f"📄 日志文件: {log_file}")

                    asyncio.run(crawler.start_crawl(keyword, max_posts, max_comments, skip_collect))
                self.log_queue.put(f"\n✅ 任务完成\n")
                self.log_queue.put(
                    f"📊 帖子: {crawler.total_posts}, 评论: {crawler.total_comments}\n"
                )
            except Exception as e:
                self.log_queue.put(f"\n❌ 任务失败: {e}\n")
            finally:
                writer.close()
                self.log_queue.put(f"\n📄 日志已保存到: {log_file}\n")
                self.log_queue.put("__TASK_DONE__")

        threading.Thread(target=worker, daemon=True).start()

    def on_continue(self):
        """用户点击继续"""
        crawler = self._get_active_crawler()
        if crawler is None:
            messagebox.showwarning("提示", "爬虫尚未初始化")
            return

        self._append_log("\n👆 用户确认继续，开始爬取...\n")
        crawler.request_continue()

        # 切换到爬取状态
        self._set_running(True, waiting_login=False)

    def on_pause(self):
        crawler = self._get_active_crawler()
        if crawler is None:
            return

        self.task_paused = not self.task_paused
        crawler.set_paused(self.task_paused)

        if self.task_paused:
            self.pause_btn.configure(text="▶ 继续")
            self._set_state("已暂停")
        else:
            self.pause_btn.configure(text="⏸ 暂停")
            self._set_state("运行中")

    def on_stop(self):
        crawler = self._get_active_crawler()
        if crawler:
            crawler.stop()
        self._append_log("\n⏹ 正在停止...\n")


def main():
    app = DoubanGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
