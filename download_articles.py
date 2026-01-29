import asyncio
from asyncio import Queue

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser
from aiosqlite import connect

from scrape.article import search_articles, fetch_article_info
from dao.article import all_articles


MAX_PAGE_COUNT = 3
CATEGORY = "体育"
KEYWORD = "篮球"
HEADLESS = False

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    # 'Host': 'so.toutiao.com',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main():
    async with (
        async_playwright() as p,
        connect('data.db') as conn,
    ):
        browser: Browser = await p.chromium.launch(headless=HEADLESS)
        page_queue: Queue[Page] = Queue()
        for _ in range(MAX_PAGE_COUNT):
            page = await browser.new_page(
                extra_http_headers=HEADERS,
            )
            await page_queue.put(page)
        await search_articles(page_queue, conn, CATEGORY, KEYWORD, 0)
        articles = await all_articles(conn)
        # articles = articles[:1]
        tasks = [
            fetch_article_info(page_queue, conn, article)
            for article in articles
        ]
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
