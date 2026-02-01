import asyncio
from typing import AsyncGenerator
from asyncio import Lock, Semaphore
from pathlib import Path
from logging import getLogger, basicConfig, INFO
from random import uniform, randint
from contextlib import asynccontextmanager
import re

from playwright.async_api import Page, Browser, BrowserContext
from playwright.async_api import expect
from playwright_stealth.stealth import Stealth

from aiosqlite import Connection

from dao.user import User
from dao.user import update_cookies, insert_user
from dao.article import Article
from utils import is_login
from llm_utils import llm_rewrite_content, llm_rewrite_title, llm_rewrite_article


DOMAIN_WWW = 'https://www.toutiao.com/'
DOMAIN_MP = 'https://mp.toutiao.com/'
TIMEOUT = 1000000
TERMINAL_LOCK = Lock()  # 与用户的交互锁

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    # 'Host': 'so.toutiao.com',
    'Referer': 'https://www.toutiao.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
}


# 限制每个账号同一时刻只能对应一个context
USER_LOCKS: dict[str, Lock] = {}


@asynccontextmanager
async def user_context(
    user: User,
    browser: Browser,
    extra_headers: dict | None = None
) -> AsyncGenerator[BrowserContext, None]:
    '''
    通过用户的cookies登录，获取其对应的BrowserContext对象

    如果用户cookies为空，则返回一个无额外cookies的context

    NOTE: 如果用户的cookies过期，改函数不会报错，也不会警告，请注意。

    :param user: 用户对象
    :param browser: 浏览器对象
    :param extra_headers: 额外的请求头
    :return: 携带用户信息的BrowserContext对象
    '''
    phone = user.phone
    if phone not in USER_LOCKS:
        USER_LOCKS[phone] = Lock()
    lock = USER_LOCKS[phone]
    async with lock:
        context = await browser.new_context(no_viewport=True)
        if extra_headers is not None:
            await context.set_extra_http_headers(extra_headers)
        if not len(user.cookies):
            LOGGER.warning(f'用户"{phone}"的cookies为空，请先登录获取')
            yield context
        else:
            await context.add_cookies(user.cookies)   # type: ignore[arg-type]
            yield context
        await context.close()


@asynccontextmanager
async def user_page(
    user: User,
    browser: Browser,
    *,
    extra_headers: dict | None = None,
) -> AsyncGenerator[Page, None]:
    '''
    通过用户的cookies登录，获取其对应的Page对象

    其实就是对user_context的封装，只是返回值是Page对象

    :param user: 用户对象
    :param browser: 浏览器对象
    :param extra_headers: 额外的请求头
    :return: 携带用户信息的Page对象
    '''
    stealth = Stealth()
    async with user_context(user, browser, extra_headers) as context:
        page = await context.new_page()
        await stealth.apply_stealth_async(page)
        yield page
        await page.close()


@asynccontextmanager
async def user_multi_pages(
    user: User,
    browser: Browser,
    num: int,
    extra_headers: dict | None = None,
) -> AsyncGenerator[list[Page], None]:
    '''
    通过用户的cookies登录，获取其对应的Page对象列表

    其实就是对user_context的封装，只是返回值是Page对象列表

    老实说，我现在还不知道这个manager在哪里能用到

    但是也就几行，先写了再说

    :param user: 用户对象
    :param browser: 浏览器对象
    :param extra_headers: 额外的请求头
    :return: 携带用户信息的Page对象列表
    '''
    async with user_context(user, browser, extra_headers) as context:
        pages = await asyncio.gather(*[
            context.new_page()
            for _ in range(num)
        ], return_exceptions=True)
        pages = [page for page in pages if isinstance(page, Page)]
        yield pages
        await asyncio.gather(*[
            page.close()
            for page in pages
        ])


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
        async with TERMINAL_LOCK:
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


async def upload_article(
    browser: Browser,
    user: User,
    article: Article,
    semaphore: Semaphore,
    rewrite: bool = True
) -> bool:
    LOGGER.info(f'原文章链接：{article.url}')
    LOGGER.info(f'原文章标题：{article.title}')
    context = await browser.new_context()
    cookies = user.cookies
    await context.add_cookies(cookies)  # type: ignore
    await context.set_extra_http_headers(HEADERS)
    async with semaphore:
        page = await context.new_page()
        await page.goto(
            f'{DOMAIN_MP}profile_v4/graphic/publish?from=toutiao_pc',
            wait_until='networkidle',
            timeout=TIMEOUT
        )
        # 第领步：关闭烦人的ai助手
        close_btn = page.locator('svg.close-btn')
        await close_btn.wait_for(state='visible')
        await close_btn.click()
        await asyncio.sleep(uniform(0.5, 2.5))
        await page.wait_for_load_state('networkidle')
        # 第一步：输入标题
        if rewrite:
            article.title = await llm_rewrite_title(article.title)
        await page.fill('div.editor-title textarea', article.title)
        await asyncio.sleep(uniform(0.5, 2.5))
        # 第二步：ai洗稿
        content = article.content
        if rewrite:
            content = await llm_rewrite_content(article.content)
        content = content.replace('```', '```\n\n\n')
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'\[.*?\]\(.*?\)', '', content)
        # 第三步：输入正文
        # FIXME: 直接fill的话，markdown格式就丢了。
        # 试试用type
        await page.type('div.ProseMirror', content, timeout=len(content)*60)
        await asyncio.sleep(uniform(0.5, 2.5))
        # 第四步：选择上传封面
        cover_add = page.locator('div.article-cover-add')
        await cover_add.wait_for(state='visible', timeout=TIMEOUT)
        await cover_add.evaluate('(el) => el.click()')
        await asyncio.sleep(uniform(0.5, 2.5))
        await page.wait_for_load_state('networkidle')
        # 第五步：点击今日头条的免费素材库
        await page.click('div.byte-tabs-header-title:text-is("免费正版图片")')
        await asyncio.sleep(uniform(0.5, 2.5))
        await page.wait_for_load_state('networkidle')
        # 第六步：输入关键字搜索图片
        await page.fill('div.inp-search input', article.keyword)
        await page.keyboard.press('Enter')
        await asyncio.sleep(uniform(3.5, 5.5))
        await page.wait_for_load_state('networkidle')
        # 第七步：随机选择一个图片（修改后的逻辑）
        # 先获取所有span.hover-icon元素的数量
        hover_icons = page.locator("span.hover-icon")
        # 获取元素总数
        count = await hover_icons.count()
        if count <= 0:
            LOGGER.warning('未找到封面图片元素 span.hover-icon')
            return False
        nth = randint(0, count - 1)
        # 根据随机索引选择元素
        random_span = hover_icons.nth(nth)
        await random_span.wait_for(state='attached')
        await asyncio.sleep(uniform(0.5, 2.5))
        await random_span.evaluate('(el) => el.click()')
        await asyncio.sleep(uniform(0.5, 2.5))
        await page.wait_for_load_state('networkidle')
        await page.click('.ic-ui-search .byte-btn-primary')
        await asyncio.sleep(uniform(3.5, 5.5))  # 这里比较慢 多等一会儿
        await page.wait_for_load_state('networkidle')
        # 第八步：点击发布按钮
        publish_btn = page.locator('button.publish-btn-last')
        # await expect(publish_btn).to_be_visible(timeout=30000)
        for _ in range(3):
            await publish_btn.evaluate('(el) => el.click()')
            await asyncio.sleep(uniform(0.5, 2.5))
            await page.wait_for_load_state('networkidle')
        await asyncio.sleep(uniform(3.5, 5.5))  # 多等一会儿
        await page.wait_for_load_state('networkidle')
        # await page.pause()
        await page.close()
    return True


async def upload_微头条(
    browser: Browser,
    user: User,
    article: Article,
    semaphore: Semaphore,
    rewrite: bool = True,
    extra_headers: dict | None = None,
) -> bool:
    '''
    FIXME: 如果屏幕不够大，就会有个巨恶心的发文助手挡住发布按钮

    虽然中文当函数名是非常不pythonic的行为

    但是“微头条”如果翻译成"micro-blog"或者用拼音"weitoutiao"，
    都可能会让人不知所云。所以我在这里使用了中文
    '''
    
    async with (
        semaphore,
    ):
        if rewrite:
            article = await llm_rewrite_article(
                article,
                rewrite_title=False,
            )
            LOGGER.info(f'用户"{user.phone}"洗稿成功')
        async with user_page(
            user,
            browser,
            extra_headers=extra_headers,
        ) as page:
            LOGGER.info(f'用户"{user.phone}"正在上传微头条文章')
            LOGGER.info(f'原文章链接：{article.url}')
            LOGGER.info(f'原文章标题：{article.title}')
            
            await page.goto(
                f'{DOMAIN_MP}profile_v4/weitoutiao/publish?from=toutiao_pc',
                wait_until='domcontentloaded',
            )

            content = article.content
            content = content.replace('```', '```\n\n\n')
            content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
            content = re.sub(r'\[.*?\]\(.*?\)', '', content)
            editot_region = page.locator('div.ProseMirror')
            await editot_region.wait_for(state='visible')
            await editot_region.type(
                content[:2000],
                timeout=2000*30,
            )
            await asyncio.sleep(uniform(0.5, 2.5))
            await page.wait_for_load_state('networkidle')
            retry_count = 3
            i = 0
            for i in range(retry_count):
                await page.click('button.publish-content')
                await asyncio.sleep(uniform(3.5, 5.5))
                if 'publish' not in page.url:
                    LOGGER.info(f'用户"{user.phone}"的微头条文章"{article.title}"发布成功')
                    break
                else:
                    LOGGER.warning(f'用户"{user.phone}"的微头条文章"{article.title}"发布失败，正在重试')
            if i == retry_count - 1:
                LOGGER.error(f'用户"{user.phone}"的微头条文章"{article.title}"发布失败，重试{retry_count}次后仍失败')
        await asyncio.sleep(uniform(3*60, 5*60))  # 等待3-5分钟
    return True
