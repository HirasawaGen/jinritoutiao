import re
import asyncio
import sys

from aiosqlite import connect
from playwright.async_api import async_playwright


from dao.user import User
from dao.user import get_user
from scrape.user import user_page


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def main():
    phone = sys.argv[1]
    if not re.match(r'^1[3-9]\d{9}$', phone):
        print('Invalid phone number')
        return
    async with (
        async_playwright() as p,
        connect('data.db') as conn
    ):
        user = await get_user(conn, phone)
        if user is None:
            print('User not found')
            return
        browser = await p.chromium.launch(headless=False)
        async with user_page(user, browser, extra_headers=HEADERS) as page:
            await page.goto('https://www.toutiao.com/', wait_until='domcontentloaded')
            print('已登录')
            await page.pause()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('成功退出')


