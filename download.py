import asyncio
from asyncio import Queue
from pathlib import Path
from aiohttp import ClientSession

from playwright.async_api import async_playwright
from playwright.async_api import Browser, Page

from scrape.video import search, fetch_download_link, download_https_video

MAX_PAGES = 3
AIO_HTTP_SEM = asyncio.Semaphore(3)
KEYWORD = '原神'
PAGENUM = 0


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main():
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=False)
        page_queue: Queue = Queue()
        for _ in range(MAX_PAGES):
            page: Page = await browser.new_page(
                extra_http_headers=HEADERS
            )
            await page_queue.put(page)
        search_tasks = [
            search(page_queue, KEYWORD, PAGENUM)
        ]
        results = await asyncio.gather(*search_tasks)
        fetch_download_url_tasks = []
        for result in results:
            for url in result:
                fetch_download_url_tasks.append(fetch_download_link(page_queue, url))
        download_urls = await asyncio.gather(*fetch_download_url_tasks)
        await browser.close()

    async with ClientSession() as session:
        https_download_tasks = [
            download_https_video(session, url, Path('videos'))
            for url in download_urls
            if url.startswith('https')
        ]
        await asyncio.gather(*https_download_tasks)


if __name__ == '__main__':
    asyncio.run(main())
