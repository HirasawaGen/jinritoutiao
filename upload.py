import asyncio
from asyncio import Queue
from pathlib import Path
from typing import cast

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser, BrowserContext
from playwright._impl._api_structures import Cookie, SetCookieParam

import aiosqlite

from scrape.user import validate_cookies, upload_video
from dao.user import create_table, all_users, insert_user, create_table
from dao.user import User


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
        # await create_table(conn)
        # await insert_user(conn, 15929265379)
        # await insert_user(conn, 19565291025)
        browser: Browser = await p.chromium.launch(headless=False)
        await create_table(conn)
        users: list[User] = await all_users(conn)
        users = [user for user in users if user.phone.startswith('195')]
        user_pages: list[tuple[Page, User]] = []
        for user in users:
            cookies: list[Cookie] = user.cookies
            ctx: BrowserContext = await browser.new_context()
            if len(cookies):
                # all the required keys of Cookies are all appear in SetCookieParam
                # so we can safely cast it.
                await ctx.add_cookies(
                    cast(list[SetCookieParam], cookies)
                )
            page: Page = await ctx.new_page()
            user_pages.append((page, user))
        validate_cookies_tasks = [
            validate_cookies(page, user, conn)
            for page, user in user_pages
        ]
        await asyncio.gather(*validate_cookies_tasks)
        await upload_video(*user_pages[0], Path() / 'videos' / '20260127_021412.mp4')
        
        

if __name__ == '__main__':
    asyncio.run(main())
