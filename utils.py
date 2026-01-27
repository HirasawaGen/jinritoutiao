from typing import AsyncIterator
from contextlib import asynccontextmanager
from asyncio import Queue
from http.cookies import SimpleCookie
import asyncio

from playwright._impl._api_structures import SetCookieParam
from playwright.async_api import Page
from bs4 import BeautifulSoup


@asynccontextmanager
async def queue_elem[T](queue: Queue[T]) -> AsyncIterator[T]:
    '''
    异步上下文管理器，用于从队列中获取元素，并在完成后放回队列中

    :param queue: 队列
    '''
    elem: T = await queue.get()
    yield elem
    await queue.put(elem)


def cookies2plawrightfmt(
    cookie_txt: str,
    domain: str = 'www.toutiao.com'
) -> list[SetCookieParam]:
    '''
    将 cookies 字符串转换为 plawright 格式的 cookies 字典

    :param cookies: cookies 字符串
    '''
    cookies = SimpleCookie()
    cookies.load(cookie_txt)
    return [{
        'name': key,
        'value': morsel.value,
        'domain': domain,
        'path': '/',
    } for key, morsel in cookies.items()]


async def is_login(今日头条: BeautifulSoup | Page) -> bool:
    '''
    判断是否登录今日头条

    :param soup_今日头条: 今日头条的 BeautifulSoup | Page 对象
    '''
    if isinstance(今日头条, Page):
        html_content = await 今日头条.content()
        今日头条 = BeautifulSoup(html_content, 'lxml')
    return 今日头条.select_one('div.user-icon') is not None


