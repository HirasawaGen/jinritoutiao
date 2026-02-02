import asyncio
from asyncio import Queue
from pathlib import Path
from random import shuffle
from typing import Awaitable
from itertools import chain

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser, BrowserContext
from playwright_stealth import Stealth
from aiosqlite import connect
from logging import getLogger, basicConfig, INFO
import yaml

from scrape.article import search_articles, fetch_article_info
from dao.article import Article
from dao.article import all_articles, create_table_article, get_articles


HEADLESS = False

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    # 'Host': 'so.toutiao.com',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main():
    catg_keywords_file = Path() / 'catg_keywords.yaml'
    config_file = Path() / 'config.yaml'
    if not catg_keywords_file.exists():
        LOGGER.error(f'分类关键字文件 {catg_keywords_file} 不存在')
        return
    if not config_file.exists():
        LOGGER.error(f'配置文件 {config_file} 不存在')
        return
    catg_keywords: dict[str, list[str]] = yaml.safe_load(catg_keywords_file.read_text(encoding='utf-8'))
    config: dict = yaml.safe_load(config_file.read_text(encoding='utf-8'))
    playwright_config = config.get('playwright', {})
    async with (
        async_playwright() as p,
        connect('data.db') as conn,
    ):
        await create_table_article(conn)
        browser: Browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context()
        context.set_default_timeout(playwright_config['timeout'])
        await context.set_extra_http_headers(HEADERS)
        page_queue: Queue[Page] = Queue()
        for _ in range(playwright_config['max_pages_count']):
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            await page_queue.put(page)
        for category, keywords in catg_keywords.items():
            search_tasks: list[Awaitable[list[Article]]] = []
            for i, keyword in enumerate(keywords):
                exists = len(await get_articles(conn, category, keyword))
                LOGGER.info(f'开始获取 {category} 分类第 {i+1}/{len(keywords)} 个关键字 {keyword} 文章')
                if exists:
                    LOGGER.info(f'已存在 {category} 分类 {keyword} 文章，跳过')
                    continue
                search_tasks.extend([search_articles(
                    page_queue,
                    conn, category, keyword, i
                ) for i in range(playwright_config['max_pages_idx'])])
                await asyncio.gather(*search_tasks, return_exceptions=True)
            articles = await get_articles(conn, category)
            fetch_tasks = [
                fetch_article_info(page_queue, conn, article)
                for article in articles
            ]
            shuffle(fetch_tasks)
            await asyncio.gather(*fetch_tasks, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
