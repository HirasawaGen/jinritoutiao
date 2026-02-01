import asyncio
from asyncio import Semaphore
from pathlib import Path
from logging import getLogger, basicConfig, INFO
from itertools import batched
from random import shuffle

from playwright.async_api import async_playwright
from aiosqlite import connect
import yaml

from dao.user import User
from dao.article import Article
from dao.user import all_users
from dao.article import all_articles
from scrape.user import upload_微头条



HEADLESS = False

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


async def main():
    config_file = Path() / 'config.yaml'
    if not config_file.exists():
        LOGGER.error(f'配置文件 {config_file} 不存在')
        return
    config = yaml.safe_load(config_file.read_text(encoding='utf-8'))
    playwright_config = config.get('playwright', {})
    async with connect('data.db') as conn:
        users: list[User] = await all_users(conn)
        articles: list[Article] = await all_articles(conn)
    articles = [
        article for article in articles
        if len(article.content) > 200
        and article.uploader_fans_count < 100000
        and article.category != '游戏'
    ]
    batched_articles = batched(
        articles,
        n = len(articles) // len(users) + 1
    )
    # print(len(list(batched_articles)), len(users))
    async with (
        async_playwright() as p,
    ):
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                "--disable-blink-features=AutomationControlled",
                '--start-maximized',
            ]
        )
        users = users[3:5]
        # articles = [random.choice(articles)]
        articles = articles[:300]
        tasks = []
        semaphore = Semaphore(playwright_config['max_pages_count'])
        for user, user_articles in zip(users, batched_articles):
            LOGGER.info(f'为用户 {user.phone} 分配了 {len(user_articles)} 篇文章')
            tasks.extend([upload_微头条(
                browser,
                user,
                article,
                semaphore,
                extra_headers=HEADERS,
            )
            for article in user_articles])
        shuffle(tasks)
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
