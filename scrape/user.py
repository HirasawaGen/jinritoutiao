import asyncio
from asyncio import Lock
from pathlib import Path
from logging import getLogger, basicConfig, INFO
from random import uniform

from playwright.async_api import Page
from playwright.async_api import expect

from aiosqlite import Connection

from dao.user import User
from dao.user import update_cookies, insert_user
from utils import queue_elem, is_login


DOMAIN_WWW = 'https://www.toutiao.com/'
DOMAIN_MP = 'https://mp.toutiao.com/'
TIMEOUT = 1000000
USER_LOCK = Lock()  # 与用户的交互锁

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


# TODO: add semaphore to limit concurrent requests
async def validate_cookies(page: Page, user: User, conn: Connection) -> User:
    '''
    验证cookies是否存在且有效，不存在则登录账号，无效则更新cookies

    非常遗憾，由于今日头条只能手机验证码登录，所以该步骤目前无法完全自动化。

    但是第一次登录后，直到cookie过期前都不需要再次登录。

    FIXME: 有可能www.toutiao.com的cookies没过期，但是mp.toutiao.com的cookies过期了，代码没有考虑到这种情况，得改改。
    这个代码保存新帐号的cookies的功能应该没什么问题了，但是更新cookies的功能还需要改。
    '''
    phone = user.phone
    url = page.url
    cookies = user.cookies
    if url != DOMAIN_WWW:
        await page.goto(DOMAIN_WWW, wait_until='load', timeout=TIMEOUT)
    if not len(cookies):
        LOGGER.info(f'用户"{phone}"第一次登录，请手动获取验证码登录')
    else:
        login_flag = await is_login(page)
        if login_flag:
            LOGGER.info(f'用户"{phone}"已经登录过，无需再次登录')
            return user
        LOGGER.warning(f'用户"{phone}" cookie过期，正在自动填充相关信息')
    await page.wait_for_load_state('load')
    login_btn = page.locator('a.login-button').filter(visible=True).first
    await expect(login_btn).to_be_visible()
    # 1. 自动点击登录按钮
    await login_btn.click()
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('load')
    # 2. 自动输入手机号码
    await page.fill('input[name="normal-input"]', str(phone))
    await asyncio.sleep(uniform(0.5, 2.5))
    await page.wait_for_load_state('load')
    # 3. 自动同意协议
    await page.click('span[class="web-login-confirm-info__checkbox"]')
    # 4. 自动点击获取验证码 确保每次只有一个协程点击
    got_capcha = False
    code = ''
    while not got_capcha:
        async with USER_LOCK:
            await page.click('span.send-input')
            # TODO: 要不这里改成input，让用户在命令行输，而不是打开浏览器？
            LOGGER.info(f'已按下获取验证码按钮，请查看手机号"{phone}"的验证码')
            LOGGER.info(f'')
            while True:
                code = input(f'请输入手机号"{phone}"收到的验证码，若长时间未收到验证码请输入"N"(大写)：')
                if code == 'N':
                    LOGGER.warning('未收到验证码，60s后将重新尝试')
                    await asyncio.sleep(60)
                    break
                if code.isnumeric():
                    got_capcha = True
                    break
                if not code.isnumeric():
                    LOGGER.warning('验证码只能是数字')
                    continue
    await asyncio.sleep(uniform(0.5, 2.5))
    LOGGER.info(f'手机号"{phone}"收到的验证码："{code}"')
    # 5. 自动输入验证码
    await page.fill('input.web-login-button-input__input', code)
    await asyncio.sleep(uniform(0.5, 2.5))
    # 6. 按下登录
    await page.click('button.web-login-button')
    # 7. 获取www.toutiao.com的cookies
    cookies = await page.context.cookies(DOMAIN_WWW)
    LOGGER.info(f'已获取到用户"{phone}"在"{DOMAIN_WWW}"的cookies')
    await asyncio.sleep(uniform(0.5, 2.5))
    # 8. 跳转到mp.toutiao.com
    locator = page.locator('//a[text()="发布作品"]')
    await expect(locator).to_be_visible()
    await locator.click()
    LOGGER.info(f'正在跳转到"{DOMAIN_MP}"，并获取cookies')
    await page.wait_for_load_state('domcontentloaded')
    # 9. 获取mp.toutiao.com的cookies
    cookies_mp = await page.context.cookies(DOMAIN_MP)
    LOGGER.info(f'已获取到用户"{phone}"在"{DOMAIN_MP}"的cookies')
    # 先插入用户
    await insert_user(conn, user)
    user.cookies = [*cookies, *cookies_mp]
    # 再更新cookies
    # 因为直接插入用户的话，如果数据库中已存在该用户，则会跳过插入逻辑
    # 导致cookies未更新
    await update_cookies(conn, phone, user.cookies)
    return user


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
            await page.pause()
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