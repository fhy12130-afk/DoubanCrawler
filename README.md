# DoubanCrawler 🕷️

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40%2B-green)](https://playwright.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

基于 Playwright 的豆瓣关键词搜索爬虫，带 GUI 图形界面。

## ✨ 功能特性

- 🔍 **关键词搜索** - 直接在豆瓣搜索，不按小组
- 🌐 **自动打开浏览器** - 无需手动填 Cookie，用户手动登录
- 🔐 **自动检测验证码** - 等待手动完成后继续
- 💬 **评论采集** - 每个帖子可配置评论数量，支持翻页
- 💾 **数据保存** - 保存到 MediaCrawler/data/douban/json/（兼容格式）
- ⏯ **暂停/继续/停止** - 支持断点续爬
- 📊 **实时日志显示** - GUI 实时显示爬取进度

## 🚀 快速开始

### 方式一：双击启动（Windows）

直接双击 `启动GUI.bat` 即可。

### 方式二：命令行启动

```bash
# 克隆项目
git clone https://github.com/你的用户名/DoubanCrawler.git
cd DoubanCrawler

# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 启动 GUI
python douban_gui.py
```

## 🎮 使用方法

1. **输入关键词** - 在"搜索关键词"框输入要搜索的词
2. **设置数量** - 最大帖子数、每帖评论数
3. **点击「开始爬取」** - 浏览器会自动打开豆瓣首页
4. **手动登录** - 在浏览器中完成登录（扫码或账号密码）
5. **点击「继续爬取」** - 登录完成后点击此按钮
6. **处理验证码** - 如出现验证码，手动完成后程序自动继续

## 🎮 操作按钮

| 按钮 | 说明 |
|------|------|
| ▶ 开始爬取 | 启动爬虫，打开浏览器 |
| ▶ 继续爬取 | 登录完成后点击此按钮 |
| ⏸ 暂停 | 暂停当前任务 |
| ⏹ 停止 | 停止爬取并保存数据 |
| 清空日志 | 清空日志区域 |

## 📁 输出文件

爬取完成后，数据保存在 MediaCrawler 的数据目录

```
MediaCrawler/data/douban/json/
├── search_contents_2026-03-08.json  # 帖子数据
└── search_comments_2026-03-08.json  # 评论数据
```

### 数据格式

与 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的数据格式统一

**帖子数据**
```json
{
  "note_id": "帖子ID",
  "title": "帖子标题",
  "content": "帖子内容",
  "time": 时间戳,
  "time_str": "发布时间",
  "nickname": "作者",
  "liked_count": "点赞数",
  "note_url": "帖子链接",
  "source_keyword": "搜索关键词",
  "platform": "douban"
}
```

**评论数据**
```json
{
  "comment_id": "评论ID",
  "note_id": "所属帖子ID",
  "nickname": "评论者",
  "content": "评论内容",
  "create_time": 时间戳,
  "time_str": "评论时间",
  "platform": "douban"
}
```

## 📁 项目结构

```
DoubanCrawler/
├── douban_gui.py          # GUI 主程序（入口）
├── douban_crawler.py      # 命令行版本
├── config.py              # 配置文件
├── requirements.txt       # 依赖列表
├── 启动GUI.bat            # Windows 启动脚本
├── README.md              # 使用说明
├── TECHNICAL_ROADMAP.md   # 技术路线文档
├── DEVELOPMENT_LOG.md     # 开发日志
├── .gitignore             # Git 忽略文件
├── logs/                  # 日志目录（不提交）
└── data/                  # 数据目录（不提交）
```

## ⚙️ 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 主要编程语言 |
| Playwright | 1.40+ | 浏览器自动化框架 |
| BeautifulSoup4 | 4.12+ | HTML 解析 |
| lxml | 4.9+ | XML/HTML 解析后端 |
| tkinter | 内置 | GUI 界面 |

## ⚠️ 注意事项

1. **浏览器窗口会自动打开**，不要关闭它
2. **遇到验证码时手动处理**，完成后程序自动继续
3. **建议延迟 4-8 秒**，避免被限制
4. **支持断点续爬**：勾选「使用已缓存的帖子链接」+ 已有数据会自动跳过已爬取的帖子

## 📄 License

MIT License - 仅供学习研究使用。

## 🙏 致谢

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) - 数据格式参考
- [Playwright](https://playwright.dev/python/) - 浏览器自动化框架
