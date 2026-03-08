# -*- coding: utf-8 -*-
"""
豆瓣爬虫 - 使用 Playwright 控制真实浏览器
参考 MediaCrawler 的策略
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import random
import time
import re
import asyncio
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup

from config import *


class DoubanCrawler:
    """豆瓣爬虫类 - 使用 Playwright"""

    def __init__(self):
        # 保存到 MediaCrawler 的 data 目录
        self.data_dir = Path("../MediaCrawler/data/douban/json")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 统计数据
        self.total_posts = 0
        self.total_comments = 0

        # 数据列表
        self.posts_data = []
        self.comments_data = []

        # Playwright
        self.browser: Browser = None
        self.page: Page = None

    async def _random_delay(self, min_sec=None, max_sec=None):
        """随机延迟"""
        min_delay = min_sec or REQUEST_DELAY_MIN
        max_delay = max_sec or REQUEST_DELAY_MAX
        delay = random.uniform(min_delay, max_delay)
        print(f"    ⏳ 等待 {delay:.1f} 秒...")
        await asyncio.sleep(delay)

    async def setup_browser(self):
        """启动浏览器"""
        print("\n🌐 启动浏览器...")

        playwright = await async_playwright().start()

        # 使用 Chrome 浏览器（用户可能已登录）
        self.browser = await playwright.chromium.launch(
            headless=False,  # 显示浏览器，方便处理验证码
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        # 创建上下文，模拟真实用户
        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=random.choice(USER_AGENTS),
        )

        # 设置 Cookie
        if COOKIES:
            cookies = self._parse_cookies(COOKIES)
            await context.add_cookies(cookies)

        self.page = await context.new_page()

        print("✅ 浏览器已启动")

    def _parse_cookies(self, cookie_str: str) -> list:
        """解析 Cookie 字符串"""
        cookies = []
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                name, value = item.split("=", 1)
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".douban.com",
                        "path": "/",
                    }
                )
        return cookies

    async def _check_and_handle_captcha(self):
        """检查并处理验证码"""
        content = await self.page.content()

        # 检测验证码关键词
        captcha_keywords = ["验证码", "captcha", "verify", "安全验证", "人机验证"]
        has_captcha = any(kw in content for kw in captcha_keywords)

        if has_captcha:
            print("\n  🔐 检测到验证码！")
            print("  📌 请在浏览器窗口中完成验证码...")
            print("  📌 完成后，爬虫会自动继续")
            print("  ⏳ 等待中...")
            
            # 等待用户完成验证码（最多等待 5 分钟）
            for i in range(300):
                await asyncio.sleep(1)
                current_content = await self.page.content()
                if not any(kw in current_content for kw in captcha_keywords):
                    print("  ✅ 验证码已完成！")
                    await self._random_delay(2, 4)
                    return True
                
                # 每 30 秒提示一次
                if i > 0 and i % 30 == 0:
                    print(f"  ⏳ 已等待 {i} 秒...")
            
            print("  ⚠️  验证码等待超时")
            return False
        
        return True

    async def get_group_posts(self, group_id: str, page_num: int = 0) -> list:
        """获取小组帖子列表"""
        url = f"https://www.douban.com/group/{group_id}/discussion?start={page_num * 25}&type=new"

        print(f"    🌐 访问: {url}")
        await self.page.goto(url, wait_until="load", timeout=60000)

        # 检查验证码
        if not await self._check_and_handle_captcha():
            return []

        await self._random_delay()

        # 解析页面
        content = await self.page.content()
        soup = BeautifulSoup(content, "lxml")

        table = soup.find("table", class_="olt")
        if not table:
            print("    ⚠️  未找到帖子列表")
            return []

        posts = []
        rows = table.find_all("tr")[1:]

        for row in rows:
            try:
                tds = row.find_all("td")
                if len(tds) < 4:
                    continue

                title_link = tds[0].find("a")
                if not title_link:
                    continue

                title = title_link.get("title", "") or title_link.get_text(strip=True)
                post_url = title_link.get("href", "")

                author_link = tds[1].find("a")
                author = author_link.get_text(strip=True) if author_link else ""
                reply_count = tds[2].get_text(strip=True) if len(tds) > 2 else "0"
                post_time = tds[3].get_text(strip=True) if len(tds) > 3 else ""

                topic_id = ""
                match = re.search(r"/topic/(\d+)/", post_url)
                if match:
                    topic_id = match.group(1)

                posts.append(
                    {
                        "topic_id": topic_id,
                        "title": title,
                        "url": post_url,
                        "author": author,
                        "reply_count": reply_count,
                        "post_time": post_time,
                        "group_id": group_id,
                    }
                )

            except Exception:
                continue

        return posts

    async def get_topic_detail(self, post_info: dict) -> bool:
        """获取帖子详情和评论"""
        topic_url = post_info.get("url", "")
        if not topic_url:
            return False

        await self.page.goto(topic_url, wait_until="load", timeout=60000)

        # 检查验证码
        if not await self._check_and_handle_captcha():
            return False

        content = await self.page.content()
        soup = BeautifulSoup(content, "lxml")

        # 解析帖子
        topic_doc = soup.find("div", class_="topic-doc")
        if not topic_doc:
            return False

        # 帖子基本信息
        title_elem = soup.find("h1")
        title = (
            title_elem.get_text(strip=True)
            if title_elem
            else post_info.get("title", "")
        )

        from_elem = topic_doc.find("span", class_="from")
        author = ""
        if from_elem:
            author_link = from_elem.find("a")
            author = author_link.get_text(strip=True) if author_link else ""

        time_elem = topic_doc.find("span", class_="create-time")
        post_time = (
            time_elem.get_text(strip=True)
            if time_elem
            else post_info.get("post_time", "")
        )

        content_div = soup.find("div", id="link-report")
        post_content = ""
        if content_div:
            for tag in content_div.find_all(["script", "style"]):
                tag.decompose()
            post_content = content_div.get_text(strip=True)

        # 点赞数
        like_count = "0"
        react_elem = soup.find("div", class_="action-react")
        if react_elem:
            react_num = react_elem.find("span", class_="react-num")
            like_count = react_num.get_text(strip=True) if react_num else "0"

        # 构建帖子数据
        post_data = {
            "note_id": post_info.get("topic_id", ""),
            "type": "group",
            "title": title,
            "desc": post_content[:500] if post_content else "",
            "content": post_content,
            "time": self._parse_time_to_timestamp(post_time),
            "time_str": post_time,
            "user_id": "",
            "nickname": author,
            "avatar": "",
            "liked_count": like_count,
            "comment_count": post_info.get("reply_count", "0"),
            "group_id": post_info.get("group_id", ""),
            "note_url": topic_url,
            "source_keyword": KEYWORDS,
            "platform": "douban",
        }

        self.posts_data.append(post_data)
        self.total_posts += 1

        # 解析评论
        comments = self._parse_comments(soup, post_info.get("topic_id", ""))
        self.comments_data.extend(comments)
        self.total_comments += len(comments)

        await self._random_delay()

        return True

    def _parse_comments(self, soup: BeautifulSoup, topic_id: str) -> list:
        """解析评论"""
        comments = []

        comments_list = soup.find("ul", id="comments")
        if not comments_list:
            return comments

        comment_items = comments_list.find_all("li", recursive=False)

        for item in (
            comment_items[:MAX_COMMENTS_PER_POST]
            if MAX_COMMENTS_PER_POST > 0
            else comment_items
        ):
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
                    comment["create_time"] = self._parse_time_to_timestamp(time_str)
                    comment["time_str"] = time_str

                    content_elem = reply_doc.find("p", class_="reply-content")
                    comment["content"] = (
                        content_elem.get_text(strip=True) if content_elem else ""
                    )

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

    def _parse_time_to_timestamp(self, time_str: str) -> int:
        """将时间字符串转换为毫秒时间戳"""
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

    async def crawl_group(self, group_id: str):
        """爬取指定小组"""
        print(f"\n{'=' * 60}")
        print(f"📁 开始爬取小组: {group_id}")
        print(f"{'=' * 60}")

        page_num = 0
        group_posts = 0

        while group_posts < MAX_POSTS_PER_KEYWORD:
            print(f"\n📄 正在获取第 {page_num + 1} 页...")

            posts = await self.get_group_posts(group_id, page_num)

            if not posts:
                print(f"  ✅ 没有更多帖子了")
                break

            for post in posts:
                if group_posts >= MAX_POSTS_PER_KEYWORD:
                    break

                print(f"\n  📝 [{group_posts + 1}] {post['title'][:40]}...")

                if await self.get_topic_detail(post):
                    group_posts += 1
                    comment_count = len(
                        [
                            c
                            for c in self.comments_data
                            if c.get("note_id") == post.get("topic_id")
                        ]
                    )
                    print(f"    ✅ 成功 (评论数: {comment_count})")
                else:
                    print(f"    ⏭️  跳过")

                # 每爬完 10 个帖子保存一次
                if group_posts % 10 == 0:
                    self.save_data()

            page_num += 1

        print(f"\n✅ 小组 {group_id} 完成: {group_posts} 个帖子")

    def save_data(self):
        """保存数据"""
        timestamp = datetime.now().strftime("%Y-%m-%d")

        contents_file = self.data_dir / f"search_contents_{timestamp}.json"
        with open(contents_file, "w", encoding="utf-8") as f:
            json.dump(self.posts_data, f, ensure_ascii=False, indent=2)

        comments_file = self.data_dir / f"search_comments_{timestamp}.json"
        with open(comments_file, "w", encoding="utf-8") as f:
            json.dump(self.comments_data, f, ensure_ascii=False, indent=2)

    async def run(self):
        """运行爬虫"""
        print("\n" + "=" * 60)
        print("🕷️  豆瓣爬虫启动 (Playwright 版本)")
        print("=" * 60)
        print(
            f"🎯 目标: {MAX_POSTS_PER_KEYWORD} 帖子/小组, {MAX_COMMENTS_PER_POST} 评论/帖子"
        )
        print(f"📁 小组: {GROUP_IDS}")
        print(f"⏱️  延迟: {REQUEST_DELAY_MIN}-{REQUEST_DELAY_MAX} 秒")
        print(f"💾 保存到: MediaCrawler/data/douban/json/")
        print("=" * 60)

        start_time = datetime.now()

        await self.setup_browser()

        for group_id in GROUP_IDS:
            await self.crawl_group(group_id)

        # 最终保存
        self.save_data()

        # 关闭浏览器
        if self.browser:
            await self.browser.close()

        # 统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("📊 爬取统计")
        print("=" * 60)
        print(f"✅ 总帖子数: {self.total_posts}")
        print(f"✅ 总评论数: {self.total_comments}")
        print(f"⏱️  耗时: {duration:.1f} 秒 ({duration / 60:.1f} 分钟)")

        if self.posts_data:
            print(f"\n💾 数据已保存:")
            print(f"   - 帖子: {self.data_dir}/search_contents_*.json")
            print(f"   - 评论: {self.data_dir}/search_comments_*.json")
        print("=" * 60)


async def main():
    crawler = DoubanCrawler()
    await crawler.run()


if __name__ == "__main__":
    asyncio.run(main())
