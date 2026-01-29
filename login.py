import asyncio
import sys
from pathlib import Path
import re

from playwright.async_api import async_playwright
from playwright.async_api import Page, Browser, BrowserContext

import aiosqlite

from scrape.user import validate_cookies
from dao.user import create_table_users, all_users, create_table_users, insert_user
from dao.user import User


MAX_PAGES = 1
DOMAIN = 'https://www.toutiao.com'
WAIT_TIME = 1000000


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


async def page_with_cookies[C](browser: Browser, cookies: list[C]) -> Page:
    context = await browser.new_context()
    await context.add_cookies(cookies)  # type: ignore
    page = await context.new_page()
    return page


async def main():
    phones_txt = Path() / 'phones.txt'
    if not phones_txt.exists():
        print('请先创建phones.txt文件，并逐行把手机号写进去')
        exit(0)
    phone_pattern = re.compile(r'^1[3-9]\d{9}$')
    phones = [line.strip() for line in phones_txt.read_text().split('\n') if len(line.strip())]
    wrong_phones = [phone for phone in phones if not phone_pattern.match(phone)]
    phones = [phone for phone in phones if phone_pattern.match(phone)]
    for wrong_phone in wrong_phones:
        print(f'手机号"{wrong_phone}"格式不正确，已忽略')
    print(f'共有{len(phones)}个手机号需要验证')
    if not len(phones):
        print('没有需要登录的手机号')
        exit(0)
    async with (
        aiosqlite.connect('data.db') as conn,
        async_playwright() as p
    ):
        await create_table_users(conn)
        for phone in phones:
            user = User(phone=phone)
            await insert_user(conn, user)
        users = await all_users(conn)
        users = [user for user in users if user.phone in phones]
        browser: Browser = await p.chromium.launch(headless=False)
        tasks = [
            validate_cookies(await page_with_cookies(browser, user.cookies), user, conn)
            for user in users
        ]
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
        