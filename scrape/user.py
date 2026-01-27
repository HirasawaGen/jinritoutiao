import asyncio
from asyncio import Queue
from logging import getLogger, basicConfig, INFO
from random import uniform

from playwright.async_api import Page
from playwright.async_api import expect

from aiosqlite import Connection

from dao.user import User
from dao.user import update_cookies
from utils import queue_elem, is_login


DOMAIN = 'https://www.toutiao.com/'
TIMEOUT = 1000000

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


# TODO: add semaphore to limit concurrent requests
async def validate_cookies(page: Page, user: User, conn: Connection):
    '''
    验证cookies是否存在且有效，不存在则登录账号，无效则更新cookies

    非常遗憾，由于今日头条只能手机验证码登录，所以该步骤目前无法完全自动化。

    但是第一次登录后，直到cookie过期前都不需要再次登录。
    '''
    phone = user.phone
    url = page.url
    cookies = user.cookies
    if not url == DOMAIN:
        await page.goto(DOMAIN, wait_until='networkidle', timeout=TIMEOUT)
    if cookies is None:
        LOGGER.info(f'用户"{phone}"第一次登录，请手动获取验证码登录')
    else:
        login_flag = await is_login(page)
        if login_flag:
            LOGGER.info(f'用户"{phone}"已经登录过，无需再次登录')
            return
        LOGGER.warning(f'用户"{phone}" cookie过期，正在自动填充相关信息')
    login_btn = page.locator('a.login-button').filter(visible=True).first
    await expect(login_btn).to_be_visible()
    # 点击登录按钮
    await login_btn.click()
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 输入手机号码
    await page.fill('input[name="normal-input"]', str(phone))
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 手动点击获取验证码
    LOGGER.info(f'请手动获取用户"{phone}"的验证码并登录')
    await page.pause()
    cookies = await page.context.cookies(DOMAIN)
    cookies_str = '; '.join([f'{c["name"]}={c["value"]}' for c in cookies if 'name' in c and 'value' in c])
    await update_cookies(conn, phone, cookies_str)
        
