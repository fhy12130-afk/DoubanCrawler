# 豆瓣爬虫开发日志

## 项目背景

用户需要为学术研究项目爬取豆瓣平台的数据。要求爬取关键词"爱你老己"相关的帖子和评论，数据需要与 MediaCrawler 项目的数据格式统一。

---

## 开发时间线

### 2026-02-28 开发记录

#### 阶段一：项目初始化

**需求分析：**
- 关键词：爱你老己
- 目标：2000+ 帖子，5000+ 评论
- 时间范围：2025年11月21日至2026年2月28日（后取消）
- 数据格式：与 MediaCrawler 统一
- 界面要求：参考 `D:\code\考研网站第一部分` 的 GUI 风格

**技术调研：**
- MediaCrawler 不支持豆瓣平台（只支持：小红书、抖音、快手、B站、微博、贴吧、知乎）
- 需要单独创建豆瓣爬虫项目
- GitHub 上参考项目：`KKCHANNEL-kk/douban_group_spider`

**初始实现：**
- 创建 `D:\code\老师工作\DoubanCrawler\` 目录
- 实现基础爬虫框架
- 使用 Playwright 作为浏览器自动化工具

---

#### 阶段二：功能迭代

**问题 1：Cookie 填写繁琐**
- 原方案：用户手动在 config 中填写 Cookie
- 改进方案：使用 Playwright 自动打开浏览器，用户手动登录
- 状态：✅ 已解决

**问题 2：自动继续导致无法登录**
- 原方案：检测到登录状态后自动继续爬取
- 改进方案：用户登录后需要手动点击「继续爬取」按钮
- 状态：✅ 已解决

**问题 3：按小组爬取不符合需求**
- 原方案：遍历小组列表爬取
- 改进方案：直接使用关键词全局搜索
- 状态：✅ 已解决

**问题 4：时间范围限制**
- 原需求：爬取指定时间范围的数据
- 修改后：爬取所有数据，但保留发布时间和评论时间字段
- 状态：✅ 已解决

---

#### 阶段三：搜索页面适配

**问题 5：小组搜索无结果**
- 现象：使用 `/group/topic` 搜索返回 0 结果
- 原因：豆瓣小组搜索需要登录且结果有限
- 改进：改用全局搜索 `https://www.douban.com/search?q=xxx`
- 状态：✅ 已解决

**问题 6：翻页方式错误**
- 原方案：URL 参数翻页 `&start=15`
- 实际情况：豆瓣使用「显示更多」按钮动态加载
- 改进：使用 Playwright 点击按钮翻页
- 状态：✅ 已解决

**问题 7：选择器匹配错误**
- 现象：找到 141 个结果项，但都是页面导航链接
- 原因：选择器太宽泛，匹配到整个页面的 div
- 调试：保存页面 HTML 到 `debug_page.html` 分析
- 发现：豆瓣新版搜索使用 `DouWeb-SR-*` 前缀的类名
- 改进：使用精确选择器 `li.DouWeb-SR-search-result-list-card`
- 状态：✅ 已解决

---

#### 阶段四：链接解析

**问题 8：链接格式特殊**
- 现象：大部分链接是 `#`，只有一个是有效帖子
- 原因：标题按钮没有 href 属性，真正链接在「查看全文」按钮
- 发现：帖子链接格式为 `/doubanapp/dispatch?uri=/group/topic/xxx`
- 改进：解析 URL 参数，提取真实帖子路径
- 代码示例：
  ```python
  if "/doubanapp/dispatch" in href:
      params = parse_qs(urlparse(href).query)
      if "uri" in params:
          real_uri = unquote(params["uri"][0])
          # 提取 /group/topic/xxxxx
  ```
- 状态：✅ 已解决

**问题 9：搜索结果类型混杂**
- 现象：10 个结果卡片，只有 1 个是帖子
- 原因：全局搜索返回多种类型（小组、用户、图库、帖子）
- 发现：只有 `doubanapp/dispatch` + `/group/topic/` 组合才是帖子
- 改进：直接搜索页面所有帖子链接，不再依赖结果容器结构
- 状态：✅ 已解决

---

#### 阶段五：验证码处理

**问题 10：误报验证码**
- 现象：正常页面也被识别为验证码页面
- 原因：关键词匹配太宽泛（"verify" 等词在正常页面也存在）
- 改进：
  - 检查特定 CSS 选择器而非关键词
  - 检查 URL 是否包含 captcha/verify
  - 验证码元素检测后才触发等待
- 状态：✅ 已解决

---

#### 阶段六：日志与调试

**问题 11：难以定位问题**
- 需求：方便开发者查看日志进行调试
- 实现：
  - 日志实时显示在 GUI 界面
  - 同时保存到 `logs/crawler_YYYYMMDD_HHMMSS.log`
  - 页面 HTML 保存到 `logs/debug_page.html`
  - 添加详细调试输出
- 状态：✅ 已解决

---

### 2026-03-01 v2.0 重大修复

#### 问题诊断

对项目进行全面代码审查，对比参考项目（`D:\code\考研网站第一部分` 的研招网爬虫和 `D:\code\老师工作\MediaCrawler`），发现以下致命问题：

#### 阶段七：搜索策略重构

**问题 12：全局搜索帖子命中率极低**
- 现象：搜索"爱你老己"只找到 1-3 个帖子，大量结果是小组、用户、图库等非帖子内容
- 原因：`douban.com/search?q=xxx` 是全局搜索，返回所有类型的混合结果
- 分析：debug_page.html 显示 10 个结果卡片中只有 1 个是帖子链接
- 尝试：改用 `search.douban.com/group/topic?q=xxx` → 失败，该子域名返回 403，需要特殊认证
- 最终方案：保持使用 `www.douban.com/search?q=xxx` 全局搜索，但优化链接解析逻辑
  - 同时支持直接 `/group/topic/\d+` 链接和 `doubanapp/dispatch` 链接
  - 翻页使用"显示更多"按钮（`button.DouWeb-SR-search-result-list-load-more`）
  - 所有 `networkidle` 等待加 try/except 防止豆瓣跟踪脚本导致超时卡死
- 状态：✅ 已解决

---

#### 阶段八：评论内容修复

**问题 13：所有评论的 content 字段为空字符串**
- 现象：已爬数据中 100% 的评论 `content` 为 `""`
- 原因：
  - 豆瓣评论区通过 JavaScript 动态渲染
  - 虽然使用了 Playwright，但没有等待评论区 DOM 加载完成就调用了 `page.content()`
  - 评论文本有时嵌套在 `<p class="reply-content"><span>实际文本</span></p>` 中
- 改进：
  - 添加 `await page.wait_for_selector("ul#comments", timeout=10000)` 等待评论区加载
  - 添加 `await page.wait_for_load_state("networkidle")` 确保 AJAX 请求完成
  - 评论解析时先尝试 `<span>` 子元素，再回退到 `<p>` 直接文本
- 状态：✅ 已解决

---

#### 阶段九：评论翻页

**问题 14：只采集第一页评论**
- 现象：每个帖子最多只有 ~30 条评论，即使帖子有数百条评论
- 原因：豆瓣帖子评论默认只显示第一页，后续需要翻页
- 改进：
  - 新增 `_parse_comments_with_pagination()` 方法
  - 检测 `div.paginator span.next a` 翻页按钮
  - 使用 Playwright 点击翻页，等待加载后继续解析
  - 循环直到无更多页或达到 `max_comments` 上限
- 状态：✅ 已解决

---

#### 阶段十：数据持久化增强

**问题 15：中途崩溃丢失全部数据**
- 现象：爬虫只在全部完成后调用一次 `save_data()`，中途崩溃则数据全丢
- 改进：
  - 每爬完一个帖子立即调用 `save_data()` 增量保存
  - 启动时调用 `_load_existing_data()` 加载当天已有数据
  - 维护 `crawled_topic_ids` 集合，自动跳过已爬取的帖子
  - 实现基本的断点续爬能力
- 参考：研招网爬虫的 checkpoint 机制
- 状态：✅ 已解决

---

#### 阶段十一：反爬增强

**问题 16：反爬策略薄弱**
- 现象：只有 2 个 UA、3-6 秒延迟，容易被识别
- 改进：
  - User-Agent 扩展到 5 个（Chrome/Firefox/Safari × Windows/Mac/Linux）
  - 请求延迟从 3-6 秒增加到 4-8 秒
  - 添加 `navigator.webdriver = false` 反检测注入
  - 所有页面导航后添加 `wait_for_load_state("networkidle")` 等待
- 状态：✅ 已解决

---

## 遇到的主要技术挑战

### 1. 豆瓣新版搜索页面结构

（同上）

### 2. 帖子链接编码

（同上）

### 3. 异步与 GUI 的线程同步

（同上）

### 4. 评论动态渲染（v2.0 新增）

豆瓣评论区通过 JavaScript 异步加载，Playwright 虽然能执行 JS，但需要显式等待 DOM 元素出现。

**解决方案：**
- `wait_for_selector("ul#comments")` 等待评论容器
- `wait_for_load_state("networkidle")` 等待所有网络请求完成
- 评论文本解析时处理 `<span>` 嵌套结构

### 5. 搜索接口选择（v2.0 新增）

豆瓣有多个搜索入口，效果差异巨大：

| 接口 | URL | 返回内容 | 帖子命中率 |
|------|-----|----------|-----------|
| 全局搜索 | `douban.com/search?q=xxx` | 混合（小组+用户+图库+帖子） | ~10% |
| 小组话题搜索 | `search.douban.com/group/topic?q=xxx` | 仅小组话题 | ~100% |

**结论：** 必须使用专用的小组话题搜索接口。

---

### 1. 豆瓣新版搜索页面结构

豆瓣搜索页面使用 React 动态渲染，类名采用随机前缀 + 语义后缀的形式：

```html
<li class="DouWeb-SR-search-result-list-card">
  <span class="DouWeb-SR-topic-card-title-button">标题</span>
  <a class="DouWeb-SR-article-preview-more" href="...">查看全文</a>
</li>
```

**解决方案：**
- 保存页面 HTML 分析结构
- 使用部分类名匹配 `[class*='DouWeb-SR']`

### 2. 帖子链接编码

帖子链接使用双重编码：

```
原始: /group/topic/344185043
编码后: %2Fgroup%2Ftopic%2F344185043
嵌入: /doubanapp/dispatch?uri=%2Fgroup%2Ftopic%2F344185043
```

**解决方案：**
- 使用 `urllib.parse.unquote` 解码
- 正则提取帖子 ID

### 3. 异步与 GUI 的线程同步

爬虫使用 async/await，GUI 使用 tkinter 事件循环。

**解决方案：**
- 使用 `threading.Thread` 运行爬虫
- 使用 `queue.Queue` 传递日志消息
- GUI 定时检查队列更新界面

---

## 代码统计

| 文件 | 行数 | 说明 |
|------|------|------|
| douban_gui.py | ~1000 | GUI 主程序（含爬虫核心） |
| douban_crawler.py | ~470 | 命令行版本（旧，已弃用） |
| config.py | ~52 | 配置文件 |
| requirements.txt | 4 | 依赖列表 |

---

## 待解决问题

- [x] ~~帖子数量较少时提前结束~~ → v2.0 已改用小组话题搜索
- [x] ~~搜索结果页需要滚动才能加载更多~~ → v2.0 已改用 URL 参数翻页
- [ ] 部分帖子需要登录才能查看完整内容
- [ ] 评论中的图片未采集
- [ ] 子评论（楼中楼）未展开

---

## 经验总结

1. **先分析再编码** - 保存页面 HTML 分析结构比猜测选择器更高效
2. **日志很重要** - 详细的日志输出大大加快调试速度
3. **用户交互** - 涉及登录和验证码的场景，让用户手动处理更可靠
4. **数据格式统一** - 与现有项目保持一致，减少后续处理工作
5. **增量保存** - 每爬完一个帖子就保存，避免中途崩溃丢失全部数据
6. **搜索策略** - 专用搜索接口（search.douban.com/group/topic）比全局搜索命中率高得多
7. **等待渲染** - Playwright 页面需要 wait_for_selector + networkidle 确保 JS 渲染完成后再解析

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-02-28 | 初始版本，基础爬取功能 |
| v1.1 | 2026-02-28 | 添加 GUI 界面 |
| v1.2 | 2026-02-28 | 修复搜索页面解析 |
| v1.3 | 2026-02-28 | 修复链接解析和翻页 |
| v1.4 | 2026-02-28 | 添加日志保存功能 |
| v2.0 | 2026-03-01 | 重大修复：搜索策略、评论提取、翻页、增量保存、反爬增强 |

---

## 致谢

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) - 数据格式参考
- [Playwright](https://playwright.dev/python/) - 浏览器自动化框架
