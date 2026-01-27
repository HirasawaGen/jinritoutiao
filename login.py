import asyncio
import sys

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser, BrowserContext

import aiosqlite

from scrape.user import validate_cookies
from dao.user import create_table, insert_user, create_table
from dao.user import User


MAX_PAGES = 1
DOMAIN = 'https://www.toutiao.com'
WAIT_TIME = 1000000


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main(phone: str):
    async with (
        aiosqlite.connect('data.db') as conn,
        async_playwright() as p
    ):
        await create_table(conn)
        browser: Browser = await p.chromium.launch(headless=False)
        context: BrowserContext = await browser.new_context(extra_http_headers=HEADERS)
        page: Page = await context.new_page()
        await insert_user(conn, phone)
        await validate_cookies(page, User(phone=phone), conn)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        exit(0)
    phone = sys.argv[1]
    asyncio.run(main(phone))
        