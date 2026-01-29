import asyncio
from asyncio import Queue, Semaphore
from urllib.parse import unquote
from pathlib import Path
from logging import getLogger, basicConfig, INFO
import time

from playwright.async_api import Page
from bs4 import BeautifulSoup, Tag
from aiohttp import ClientSession
import aiofiles

from utils import queue_elem


MAX_PAGES = 3
DOMAIN = 'https://www.toutiao.com'
WAIT_TIME = 1000000
AIO_HTTP_SEM = Semaphore(3)


LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


def _a_tag2url(a_tag: Tag) -> str:
    if not a_tag.has_attr('href'):
        return ''
    href = a_tag['href']
    if not isinstance(href, str):
        return ''
    href = href.split('/search/jump?url=')[-1]
    href = unquote(href)
    if not href.startswith('http'):
        return ''
    return href


async def search_video(page_queue: Queue[Page], keyword: str, page_num: int) -> list[str]:
    '''
    根据给定的keyword和page_num搜索今日头条，返回搜索结果的url列表
    FIXME: 直接访问可能会遇到反爬，这里改成从DOMAIN自动搜索，模拟人类操作

    :param page_queue: 页面队列
    :param keyword: 搜索关键词
    :param page_num: 页码(从0开始)
    :return: 搜索结果的url列表
    '''
    if page_num < 0:
        return []
    LOGGER.info(f'Searching keyword: "{keyword}", page_num: {page_num}')
    url = f'{DOMAIN}/search?dvpf=pc&keyword={keyword}&pd=video&page_num={page_num}'
    async with queue_elem(page_queue) as page:
        await page.goto(url, wait_until='domcontentloaded', timeout=WAIT_TIME)
        await asyncio.sleep(3)
        # 昨天还没遇到反爬，今天这里弹出滑块验证码了
        # await page.pause()
        # 怎么又没有了？？？
        locator = page.locator('a.text-underline-hover').filter(visible=True).first
        await locator.wait_for(timeout=WAIT_TIME)
        html_content = await page.content()
    LOGGER.info(f'Got all html content, parsing...')
    soup = BeautifulSoup(html_content, 'lxml')
    a_tags = soup.select('a.text-underline-hover')
    urls: list[str] = [
        _a_tag2url(a_tag)
        for a_tag in a_tags
    ]
    urls = [
        url
        for url in urls
        if len(url)
    ]
    LOGGER.info(f'Found {len(urls)} urls')
    return urls


async def fetch_download_link(page_queue: Queue[Page], url: str) -> str:
    '''
    从给定的视频url中获取视频下载链接

    :param page_queue: 页面队列
    :param url: 视频url
    :return: 视频下载链接，如果没有找到则返回空字符串
    '''
    LOGGER.info(f'Fetching download link for url: {url[:100]}... ')
    async with queue_elem(page_queue) as page:
        await page.goto(url, wait_until='domcontentloaded', timeout=WAIT_TIME)
        await asyncio.sleep(3)
        locator = page.locator('#root')
        await locator.wait_for()
        html_content = await page.content()
    LOGGER.info(f'Got all html content, parsing...')
    soup = BeautifulSoup(html_content, 'lxml')
    video_tag = soup.select_one('#root video')
    if video_tag is None:
        LOGGER.warning(f'No video tag found for url: {url}')
        return ''
    if not video_tag.has_attr('src'):
        return ''
    src = video_tag['src']
    if not isinstance(src, str):
        return ''
    if src.startswith('//'):
        return f'https:{src}'
    return src


async def download_https_video(session: ClientSession, url: str, save_dir: Path) -> bool:
    '''
    下载https协议的视频
    :return: 是否成功下载 
    '''
    if url == 'https://www.toutiao.com/':
        return False
    if not save_dir.exists():
        save_dir.mkdir(parents=True)
    async with AIO_HTTP_SEM, session.get(url) as response:
        if response.status != 200:
            LOGGER.warning(f'Failed to fetch url: {url}, status code: {response.status}')
            return False
        content_type = response.headers.get('content-type')
        if content_type is None:
            LOGGER.warning(f'Failed to fetch url: {url}, no content-type header')
            return False
        if not content_type.startswith('video/'):
            LOGGER.warning(f'Url: {url} is not a video, content-type: {content_type}')
            return False
        file_name = time.strftime('%Y%m%d_%H%M%S', time.localtime()) + '.mp4'
        file_path = save_dir / file_name
        async with aiofiles.open(file_path, 'wb') as f:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                await f.write(chunk)
        LOGGER.info(f'Downloaded video: {file_name}')
        return True


async def download_blob_video(session: ClientSession, url: str, save_dir: Path) -> bool:
    '''
    下载blob协议的视频
    :return: 是否成功下载 
    '''
    # TODO: implement this
    # use playwright to record the http response.
    if not save_dir.exists():
        save_dir.mkdir(parents=True)
    return False

