# -*- coding: utf-8 -*-
"""
豆瓣爬虫配置文件
"""

# ==================== 搜索配置 ====================
# 搜索关键词（多个用英文逗号分隔）
KEYWORDS = "爱你老己"

# ==================== 爬取数量配置 ====================
# 每个小组爬取的最大帖子数
MAX_POSTS_PER_KEYWORD = 100

# 每个帖子爬取的最大评论数（0 表示不限制）
MAX_COMMENTS_PER_POST = 50

# ==================== 豆瓣小组配置 ====================
# 小组ID可以在豆瓣小组URL中找到
# 例如：https://www.douban.com/group/blabla/ 中的 blabla
GROUP_IDS = [
    "blabla",  # 豆瓣π组
]

# ==================== 请求配置 ====================
# 请求间隔时间（秒）- 参考 MediaCrawler 的 CRAWLER_MAX_SLEEP_SEC
REQUEST_DELAY_MIN = 5
REQUEST_DELAY_MAX = 10

# 请求超时时间（秒）
REQUEST_TIMEOUT = 30

# 最大重试次数
MAX_RETRIES = 3

# ==================== 存储配置 ====================
# 数据保存路径（自动保存到 MediaCrawler/data/douban/json/）
DATA_DIR = "./data"

# ==================== 登录配置（必须设置） ====================
# 豆瓣Cookie
# 豆瓣Cookie（GUI 模式下由用户手动登录，此处仅用于命令行模式）
COOKIES = ''

# ==================== 代理配置（可选） ====================
ENABLE_PROXY = False
PROXY = ""

# ==================== User-Agent ====================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
