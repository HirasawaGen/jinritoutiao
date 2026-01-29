import asyncio

from aiosqlite import Connection
from pydantic import BaseModel

from dao.dao_utils import relate_sql


@relate_sql("""--sql
CREATE TABLE IF NOT EXISTS articles (
    `id` TEXT NOT NULL PRIMARY KEY,
    `title` TEXT NOT NULL,
    -- 文章链接
    `url` TEXT NOT NULL,
    -- content使用md格式
    `category` TEXT NOT NULL,
    `keyword` TEXT NOT NULL,
    -- 串联文字和图片 目前没发现有其他富文本
    `content` TEXT NOT NULL DEFAULT '',
    -- 点赞数 -1表示未获取
    `like_count` INTEGER NOT NULL DEFAULT -1,
    -- 评论数 -1表示未获取
    `comment_count` INTEGER NOT NULL DEFAULT -1,
    -- 收藏数 -1表示未获取
    `collect_count` INTEGER NOT NULL DEFAULT -1,
    `upload_time` DATETIME DEFAULT NULL,
    -- 初始为''，表示未获取到
    "uploader" TEXT NOT NULL DEFAULT '',
    -- 上传者的粉丝数，初始为-1，表示未获取到
    "uploader_fans_count" INTEGER DEFAULT -1
);
""")
async def create_table_article(
    sql: str,
    conn: Connection,
) -> None:
    await conn.execute(sql)
    await conn.commit()


class Article(BaseModel):
    id: str
    title: str
    url: str
    category: str
    keyword: str
    content: str = ''
    upload_time: str | None = None
    like_count: int = -1
    comment_count: int = -1
    collect_count: int = -1
    uploader: str = ''
    uploader_fans_count: int = -1


@relate_sql("""
DELETE FROM articles;
""")
async def truncate_table_article(
    sql: str,
    conn: Connection
) -> None:
    await conn.execute(sql)
    await conn.commit()


@relate_sql("""--sql
INSERT OR IGNORE INTO articles (
    `id`, `title`, `url`, `category`, `keyword`
) VALUES (
    ?, ?, ?, ?, ?
)
""")
async def insert_article(
    sql: str,
    conn: Connection,
    article: Article
) -> bool:
    '''
    往数据库存入一篇文章
    
    所有默认值均跳过

    只插入 id, title, url, category, keyword这五个字段

    :param conn: 数据库连接
    :param article: 文章对象
    :return: 插入成功返回True，否则返回False
    '''
    cur = await conn.execute(sql, (
        article.id,
        article.title,
        article.url,
        article.category,
        article.keyword
    ))
    await conn.commit()
    return cur.rowcount > 1


@relate_sql("""--sql
SELECT
    `id`,
    `title`,
    `url`,
    `category`,
    `keyword`,
    `content`,
    `upload_time`,
    `like_count`,
    `comment_count`,
    `collect_count`,
    `uploader`,
    `uploader_fans_count`
FROM articles
""")
async def all_articles(sql: str, conn: Connection) -> list[Article]:
    '''
    获取所有文章
    :param conn: 数据库连接
    :return: 文章列表
    '''
    cur = await conn.execute(sql)
    rows = await cur.fetchall()
    articles = []
    for row in rows:
        article = Article(
            id=row[0],
            title=row[1],
            url=row[2],
            category=row[3],
            keyword=row[4],
            content=row[5],
            upload_time=row[6],
            like_count=row[7],
            comment_count=row[8],
            collect_count=row[9],
            uploader=row[10],
            uploader_fans_count=row[11]
        )
        articles.append(article)
    return articles


async def update_article(
    conn: Connection,
    article: Article
) -> bool:
    '''
    更新一篇文章的相关信息

    :param conn: 数据库连接
    :param article: 文章对象
    :return: 更新成功返回True，否则返回False
    '''
    sql = """--sql
    UPDATE articles SET
        `content` = COALESCE(?, content),
        `like_count` = COALESCE(?, like_count),
        `comment_count` = COALESCE(?, comment_count),
        `collect_count` = COALESCE(?, collect_count),
        `uploader` = COALESCE(?, uploader),
        `uploader_fans_count` = COALESCE(?, uploader_fans_count)
    WHERE `id` = ?
    """
    cur = await conn.execute(sql, (
        article.content,
        article.like_count,
        article.comment_count,
        article.collect_count,
        article.uploader,
        article.uploader_fans_count,
        article.id
    ))
    await conn.commit()
    return cur.rowcount > 0