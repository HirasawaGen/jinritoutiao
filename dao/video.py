from typing import Annotated as Annt
from typing import overload
from pathlib import Path

from aiosqlite import Connection
from pydantic import BaseModel

from dao.dao_utils import relate_sql


'''
download的主要流程：
有一个对照表，我后面可以用yaml格式存储
类型是dict[str, list[str]]
表示视频类型和相关关键词的对照
比如“体育”对应的关键词有“足球、篮球、乒乓球”等

首先遍历这个字典。key为类型，遍历value
用playwright搜索value里的关键词，得到视频链接后存入数据库

此时每个video只有id title url category keyword这几个字段
具体的视频下载链接，上传者点赞数等还是需要playwright点进链接获取

下载完成后，md5和path字段都填上，并更新数据库

假如说明星这个类别有“蔡徐坤”
体育这个类别有“篮球”
搜索体育和明星都可能搜索到“蔡徐坤打篮球”的视频
那就只存一份，避免重复上传视频

不过这个脚本是dao层脚本 不考虑playwright
'''


@relate_sql("""--sql
CREATE TABLE IF NOT EXISTS videos (
    "id" TEXT PRIMARY KEY,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    -- 视频的分类，如：生活、娱乐、搞笑等
    "category" TEXT NOT NULL,
    -- 搜索视频时的关键词
    "keyword" TEXT NOT NULL,
    -- md5为空字符串说明未下载到本地
    "md5" TEXT NOT NULL DEFAULT '',
    -- path为空字符串说明未下载到本地
    -- path的格式为：f'{id}--{md5}'.mp4
    -- path可能不存在，说明视频被删了
    "path" TEXT NOT NULL DEFAULT '',
    -- 视频的下载链接，可能为空字符串，表示暂未获取到
    "download_url" TEXT NOT NULL DEFAULT '',
    -- 视频音频的下载链接，可能为空字符串，表示暂未获取到，或者音频已包含在视频中
    -- 因为今日头条有些视频是音画分离两个独立文件 有的是单独一个文件
    "audio_url" TEXT NOT NULL DEFAULT '',
    -- 通过类似‘https://www.toutiao.com/c/user/token/xxx/’
    -- 这样的url可以唯一确定一个用户，那就把后面的xxx当作uploader
    -- 初始为''，表示未获取到
    "uploader" TEXT NOT NULL DEFAULT '',
    -- 上传者的粉丝数，初始为-1，表示未获取到
    "uploader_fans_count" INTEGER DEFAULT -1,
    -- 点赞数，初始为-1，表示未获取到
    "like_count" INTEGER NOT NULL DEFAULT -1,
    -- 评论数，初始为-1，表示未获取到
    "comment_count" INTEGER NOT NULL DEFAULT -1,
    -- 收藏数，初始为-1，表示未获取到
    "collect_count" INTEGER NOT NULL DEFAULT -1,
    -- 播放量，初始为-1，表示未获取到
    "view_count" INTEGER NOT NULL DEFAULT -1,
    -- 上传时间，初始为当前时间，格式为YYYY-MM-DD HH:MM:SS
    "upload_time" DATETIME DEFAULT NULL,
    -- 视频时长，以秒为单位，初始为-1，表示未获取到
    "video_length" INTEGER NOT NULL DEFAULT -1
);
-- 不需要独立的“是否保存于本地”的字段
-- 因为path不存在就肯定是不存在了
-- 不需要独立的“是否音画分离”的字段
-- 只要是download_url存在，但audio_url不存在，就说明视频没有音画分离
""")
async def create_table_videos(sql: str, conn: Connection) -> None:
    await conn.execute(sql)
    await conn.commit()


class Video(BaseModel):
    id: str
    title: str
    url: str
    category: str
    keyword: str
    md5: str = ''
    path: Path = Path('')
    download_url: str = ''
    audio_url: str = ''
    uploader: str = ''
    like_count: int = -1
    comment_count: int = -1
    collect_count: int = -1
    view_count: int = -1
    upload_time: str = ''
    video_length: int = -1


@relate_sql("""--sql
INSERT OR IGNORE INTO videos (
    `id`, `title`, `url`, `category`, `keyword`
) VALUES (
   ?, ?, ?, ?, ?
);
""")
async def insert_video(
    sql: str,
    conn: Connection,
    video: Video,
) -> bool:
    '''
    插入视频，如果已经存在就忽略

    :param conn: sqlite3连接
    :param video: 视频对象
    :return: 插入成功返回True，否则返回False
    '''
    id_ = video.id
    title = video.title
    url = video.url
    category = video.category
    keyword = video.keyword
    cur = await conn.execute(sql, (id_, title, url, category, keyword))
    await conn.commit()
    return cur.rowcount == 1


async def update_video_params(
    conn: Connection,
    video_id: str,
    *,
    download_url: str = '',
    audio_url: str = '',

    uploader: str = '',
    uploader_fans_count: int = -1,
    
    like_count: int = -1,
    comment_count: int = -1,
    collect_count: int = -1,
    views_count: int = -1,
) -> int:
    # 第一步：
    # 如果download_url不为空，且确实不一样了
    # 就更新download_url
    # 可能会更新audio_url
    # 不更新path，做一个单独的下载视频的函数比较好

    # 第二步：
    # 更新uploader_fans_count uploader

    # 第三步：
    # 最后更新likes_count comments_count favours_count views_count

    return 0
