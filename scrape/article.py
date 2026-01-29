import asyncio
from asyncio import Queue
import random
from logging import getLogger, basicConfig, INFO
from urllib.parse import urlparse, parse_qs, unquote

from playwright.async_api import Page
from bs4 import BeautifulSoup
from aiosqlite import Connection
from markdownify import markdownify

from utils import queue_elem
from dao.article import Article
from dao.article import insert_article, create_table_article, update_article


DOMAIN = 'www.toutiao.com'

LOGGER = getLogger(__name__)
LOGGER.setLevel('INFO')
basicConfig(level=INFO)


async def search_articles(
    page_queue: Queue[Page],
    conn: Connection,
    category: str,
    keyword: str,
    page_num: int
) -> list[Article]:
    '''
    在今日头条上搜索文章

    :param page_queue: 页面队列
    :param conn: 数据库连接
    :param category: 分类
    :param keyword: 关键字
    :param page_num: 页码 (从0开始)
    '''
    if page_num < 0:
        return []
    async with queue_elem(page_queue) as page:
        LOGGER.info(f'搜索 {category} 分类 {keyword} 第 {page_num+1} 页')
        await page.goto((
            f'https://{DOMAIN}/search'
            '?source=search_subtab_switch'
            f'&keyword={keyword}'
            '&dvpf=pc'
            '&enable_druid_v2=1'
            '&pd=information'
            '&action_type=search_subtab_switch'
            f'&page_num={page_num}'
            '&from=news'
            '&cur_tab_title=news'
        ), wait_until='networkidle', timeout=300000)
        html_content = await page.content()
        await asyncio.sleep(random.uniform(1.5, 3.5))
        soup = BeautifulSoup(html_content, 'lxml')
        a_tags = soup.select('a.text-underline-hover')
        if len(a_tags) <= 2:
            # TODO: 按理说不应该啊 我都用有头playwright了
            LOGGER.warning(f'搜索 {category} 分类 {keyword} 第 {page_num+1} 页遇到反爬 请手动拖动滑块')
            await page.pause()
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'lxml')
            a_tags = soup.select('a.text-underline-hover')
    # 把page让渡给别的协程
    LOGGER.info(f'已获取 {category} 分类 {keyword} 第 {page_num+1} 页内容，共 {len(a_tags)} 条数据')
    articles = []
    for i, a_tag in enumerate(a_tags):
        href = str(a_tag.get('href', ''))
        if not href.startswith(f'https://{DOMAIN}/'):
            if not href.startswith('/'):
                href = f'/{href}'
            href = f'https://{DOMAIN}{href}'
        if href in {
            f'https://{DOMAIN}/javascript:void(0)',
            f'https://{DOMAIN}/https://www.toutiao.com'
        }:
            continue
        LOGGER.info(f'获取文章 {i+1} 链接：{href}')
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        url_inner = params.get('url', '')
        if not len(url_inner):
            LOGGER.warning(f'文章 {i+1} 链接不完整：{url_inner}')
            continue
        url = unquote(url_inner[0])
        id_ = urlparse(url).path.strip('/')
        title = a_tag.get_text(strip=True)
        article = Article(
            id=id_,
            title=title,
            url=url,
            category=category,
            keyword=keyword,
        )
        articles.append(article)

    # TODO: 存入数据库
    # 最好不要异步保存
    # await create_table_article(conn)
    for article in articles:
        await insert_article(conn, article)
    LOGGER.info(f'已全部存入数据库')
    return articles


async def fetch_article_info(
    page_queue: Queue[Page],
    conn: Connection,
    article: Article
) -> Article:
    '''
    获取搜索到的文章的详情，并更新数据库

    :param page_queue: 页面队列
    :param conn: 数据库连接
    :param article: 文章
    :return: 填充后的文章
    '''
    if len(article.content):
        LOGGER.info(f'文章 {article.id} 内容已获取，标题："{article.title[:20]}..." 跳过')
        return article
    url = article.url
    LOGGER.info(f'获取文章 {article.id} 详情')
    async with queue_elem(page_queue) as page:
        await page.goto(url, wait_until='networkidle', timeout=3000000)
        html_content = await page.content()
        await asyncio.sleep(random.uniform(1.5, 3.5))
    soup = BeautifulSoup(html_content, 'lxml')
    # 第一步：获取文章内容并转为markdown
    article_soup = soup.select_one('article.syl-article-base')
    if article_soup is None:
        LOGGER.warning(f'文章 {article.id} 内容为空')
        return article
    markdown_content = markdownify(str(article_soup))
    article.content = markdown_content
    # 第二步：获取文章发布时间
    article_meta_div = soup.select_one('div.article-meta')
    if article_meta_div is None:
        LOGGER.warning(f'文章 {article.id} 元数据为空')
        return article
    article_meta = article_meta_div.get_text(strip=True).split('·')
    if len(article_meta) < 2:
        LOGGER.warning(f'文章 {article.id} 元数据不完整')
        return article
    article.upload_time = article_meta[0].strip()
    # 第三步：获取详情（就左上角那个）
    details = soup.select_one('div.detail-side-interaction')  # 这个是点赞数、评论数、分享数等
    if details is None:
        LOGGER.warning(f'文章 {article.id} 详情数据不完整')
        return article
    # 第四步：获取点赞数
    like_span = details.select_one('div.detail-like span')
    if like_span is None:
        LOGGER.warning(f'文章 {article.id} 点赞数数据不完整')
        return article
    like_text = like_span.get_text(strip=True)
    article.like_count = int(like_text) if like_text.isdigit() else 0
    # 第五步：获取评论数
    comment_span = details.select_one('div.detail-interaction-comment span')
    if comment_span is None:
        LOGGER.warning(f'文章 {article.id} 评论数数据不完整')
        return article
    comment_text = comment_span.get_text(strip=True)
    article.comment_count = int(comment_text) if comment_text.isdigit() else 0
    # 第六步：获取收藏数
    collect_span = details.select_one('div.detail-interaction-collect span')
    if collect_span is None:
        LOGGER.warning(f'文章 {article.id} 收藏数数据不完整')
        return article
    collect_text = collect_span.get_text(strip=True)
    article.collect_count = int(collect_text) if collect_text.isdigit() else 0
    # 第七步：获取上传者信息
    user_a = soup.select_one('a.user-name')
    if user_a is None:
        LOGGER.warning(f'文章 {article.id} 作者信息数据不完整')
        return article
    user_homepage = str(user_a.get('href', ''))
    if not user_homepage.startswith(f'https://{DOMAIN}/'):
        if not user_homepage.startswith('/'):
            user_homepage = f'/{user_homepage}'
        user_homepage = f'https://{DOMAIN}{user_homepage}'
    split_path = urlparse(user_homepage).path.split('/')
    split_path = [p for p in split_path if len(p)]
    if not len(split_path):
        LOGGER.warning(f'文章 {article.id} 作者主页数据不完整')
    uploader = split_path[-1]
    article.uploader = uploader
    LOGGER.info(f'已获取文章 {article.id} 详情，标题："{article.title[:20]}..." 即将打开作者主页')
    # 第八步：打开上传者主页获取上传者粉丝数
    async with queue_elem(page_queue) as page:
        await page.goto(user_homepage, wait_until='networkidle', timeout=3000000)
        html_content = await page.content()
        await asyncio.sleep(random.uniform(1.5, 3.5))
    user_soup = BeautifulSoup(html_content, 'lxml')
    spans_num = user_soup.select('button.stat-item span.num')
    if len(spans_num) < 2:
        LOGGER.warning(f'文章 {article.id} 作者粉丝数数据不完整')
    span_num = spans_num[1]
    if span_num is None:
        LOGGER.warning(f'文章 {article.id} 作者粉丝数数据不完整')
        return article
    num = float(
        span_num.get_text(strip=True)
        .replace(',', '')
        .replace('万', '')
    )
    span_unit = span_num.select_one('span.unit')
    if span_unit is None:
        unit = 1
    else:
        # 目前好像只有以万来算的，其他单位暂时不管
        unit = {
            '万': 10000,
        }.get(span_unit.get_text(strip=True), 1)
    fans = int(num * unit)
    article.uploader_fans_count = fans
    # 第九步：更新数据库
    await update_article(conn, article)
    LOGGER.info(f'文章 {article.id} 数据库详情已更新')
    return article




