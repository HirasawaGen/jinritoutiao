import asyncio
from asyncio import Queue

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser, BrowserContext

import aiosqlite
from aiosqlite import Connection

from scrape.user import validate_cookies
from dao.user import User
from dao.user import create_table, all_users
from utils import cookies2plawrightfmt


MAX_PAGES = 1
DOMAIN = 'https://www.toutiao.com'
WAIT_TIME = 1000000


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main():
    async with (
        aiosqlite.connect('data.db') as conn,
        async_playwright() as p
    ):
        browser: Browser = await p.chromium.launch(headless=False)
        await create_table(conn)
        users: list[User] = await all_users(conn)
        user_pages: list[tuple[Page, User]] = []
        for user in users:
            cookies = user.cookies
            ctx = await browser.new_context()
            if cookies is not None:
                await ctx.add_cookies(cookies2plawrightfmt(cookies))
            page = await ctx.new_page()
            user_pages.append((page, user))
        validate_cookies_tasks = [
            validate_cookies(page, user, conn)
            for page, user in user_pages
        ]
        await asyncio.gather(*validate_cookies_tasks)
        # await insert_user(conn, 15929265379)
        # await insert_user(conn, 19565291025)
        

if __name__ == '__main__':
    asyncio.run(main())
