import asyncio
from asyncio import Lock
from pathlib import Path
from logging import getLogger, basicConfig, INFO
from random import uniform

from playwright.async_api import Page
from playwright.async_api import expect

from aiosqlite import Connection

from dao.user import User
from dao.user import update_cookies
from utils import queue_elem, is_login


DOMAIN_WWW = 'https://www.toutiao.com/'
DOMAIN_MP = 'https://mp.toutiao.com/'
TIMEOUT = 1000000
USER_LOCK = Lock()  # 与用户的交互锁

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


# TODO: add semaphore to limit concurrent requests
async def validate_cookies(page: Page, user: User, conn: Connection):
    '''
    验证cookies是否存在且有效，不存在则登录账号，无效则更新cookies

    非常遗憾，由于今日头条只能手机验证码登录，所以该步骤目前无法完全自动化。

    但是第一次登录后，直到cookie过期前都不需要再次登录。

    FIXME: 有可能www.toutiao.com的cookies没过期，但是mp.toutiao.com的cookies过期了，代码没有考虑到这种情况，得改改。
    '''
    phone = user.phone
    url = page.url
    cookies_www = user.cookies
    if url != DOMAIN_WWW:
        await page.goto(DOMAIN_WWW, wait_until='domcontentloaded', timeout=TIMEOUT)
    if not len(cookies_www):
        LOGGER.info(f'用户"{phone}"第一次登录，请手动获取验证码登录')
    else:
        login_flag = await is_login(page)
        if login_flag:
            LOGGER.info(f'用户"{phone}"已经登录过，无需再次登录')
            return
        LOGGER.warning(f'用户"{phone}" cookie过期，正在自动填充相关信息')
    login_btn = page.locator('a.login-button').filter(visible=True).first
    await expect(login_btn).to_be_visible()
    # 自动点击登录按钮
    await login_btn.click()
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 自动输入手机号码
    await page.fill('input[name="normal-input"]', str(phone))
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 自动同意协议
    await page.click('span[class="web-login-confirm-info__checkbox"]')
    # 手动点击获取验证码
    async with USER_LOCK:
        # TODO: 要不这里改成input，让用户在命令行输，而不是打开浏览器？
        LOGGER.info(f'请手动获取用户"{phone}"的验证码并登录')
        await page.pause()
    cookies_www = await page.context.cookies(DOMAIN_WWW)
    LOGGER.info(f'已获取到用户"{phone}"在"{DOMAIN_WWW}"的cookies')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    locator = page.locator('//a[text()="发布作品"]')
    await expect(locator).to_be_visible()
    await locator.click()
    LOGGER.info(f'正在跳转到"{DOMAIN_MP}"，并获取cookies')
    await page.wait_for_load_state('domcontentloaded')
    # 由DOMAIN_WWW跳转到DOMAIN_MP
    cookies_mp = await page.context.cookies(DOMAIN_MP)
    LOGGER.info(f'已获取到用户"{phone}"在"{DOMAIN_MP}"的cookies')
    await update_cookies(conn, phone, [*cookies_www, *cookies_mp])


async def upload_video(page: Page, user: User, video: Path) -> bool:
    '''
    上传视频到今日头条

    需要注意的是，用户必须登录且实名认证后才能上传视频

    但我目前不清楚如何获取是否实名认证成功。

    TODO: 目前是使用Path对象上传，后面等我给视频做了数据表和BaseModel之后，就用Video对象当video参数类型

    :param page: playwright Page对象
    :param user: User对象
    :param video: 视频文件路径 (暂时是Path对象，后面改成Video对象)
    :return: 上传成功返回True，否则返回False
    '''
    await page.goto(
        # 注意域名不是www.toutiao.com
        'https://mp.toutiao.com/profile_v4/xigua/upload-video?from=toutiao_pc',
        wait_until='networkidle',
        timeout=TIMEOUT
    )
    LOGGER.info(f'正在上传视频"{video.name}"到用户"{user.phone}"的个人主页')
    # 选择视频文件
    file_input = page.locator('input[type="file"]')
    await file_input.set_input_files(video)
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 点击发布按钮
    publish_span = page.locator("div.video-batch-footer button").locator("text=/^发布$/")
    await expect(publish_span).to_be_visible()
    # 这次点击不是真的要上传视频，只是判断是否有实名
    await publish_span.click()
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    modal_div = page.locator("div.byte-modal-content")
    if await modal_div.count():
        await expect(modal_div).to_be_visible()
        text = await modal_div.inner_text()
        if '账号信息未完善，暂时不能进行发布文章、视频等权益操作，请完善后重试' in text:
            LOGGER.warning(f'用户"{user.phone}"未实名认证，暂时无法上传视频')
            return False
    # 有实名的话就乖乖等视频发布
    try:
        await page.wait_for_selector(
            selector='span.percent:visible:has-text("上传成功")',
            timeout=1000*300,  # 5min超时
        )
    except Exception as e:
        LOGGER.error(f'上传视频失败，原因：{e}')
        return False
    LOGGER.info(f'视频"{video.name}"上传成功')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 我去 好麻烦 还得选封面
    # 先点击“选择封面”
    await page.click('div.fake-upload-trigger')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 弹出窗口后点击“本地上传”
    ul_tag = page.locator('ul.header')
    await expect(ul_tag).to_be_visible()
    await ul_tag.locator('li:nth-child(2)').click()
    # 点击完了以后上传封面图片
    cover_input = page.locator('div.m-content').locator('input[type="file"]')
    # FIXME: 这里暂时硬编码为一个图片，后面改成用ffmpeg和opencv提取视频封面
    await cover_input.set_input_files(Path() / 'cover.jpg')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 然后还得点击完成剪裁
    await page.click('div.clip-btn-content')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 点击确定
    await page.click('button.btn-sure')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 为啥还要确定一遍？？？！！！！！！
    await page.click('button.undefined')
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('networkidle')
    # 现在应该可以正式发布了
    await publish_span.click()
    # await page.pause()
    return True