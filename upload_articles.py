import asyncio
from asyncio import Semaphore
from pathlib import Path
from logging import getLogger, basicConfig, INFO

from playwright.async_api import async_playwright
from aiosqlite import connect
import yaml

from dao.user import User
from dao.article import Article
from dao.user import all_users
from dao.article import all_articles
from scrape.user import upload_article



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
    async with (
        async_playwright() as p,
        connect('data.db') as conn,
    ):
        browser = await p.chromium.launch(headless=HEADLESS)
        users: list[User] = await all_users(conn)
        articles: list[Article] = await all_articles(conn)
        articles = [
            article for article in articles
            if len(article.content) > 100
            and article.uploader_fans_count < 100000
        ]
        # users = users[:1]
        # articles = [random.choice(articles)]
        # articles = articles[:8]
        semaphore = Semaphore(playwright_config['max_pages_count'])
        for article in articles:
            upload_tasks = [
                upload_article(browser, user, article, semaphore)
                for user in users
            ]
            results = await asyncio.gather(*upload_tasks, return_exceptions=True)
            for user, result in zip(users, results):
                if result == True:
                    LOGGER.info(f'用户 {user.phone} 上传文章 {article.title} 成功')
                else:
                    LOGGER.error(f'用户 {user.phone} 上传文章 {article.title} 失败：{result}')
                
                


if __name__ == '__main__':
    asyncio.run(main())
