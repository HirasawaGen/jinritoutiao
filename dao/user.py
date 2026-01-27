from typing import Annotated as Annt
import json

from pydantic import BaseModel, Field
import aiosqlite
from aiosqlite import Connection

from dao.dao_utils import relate_sql
from playwright._impl._api_structures import Cookie, SetCookieParam


@relate_sql("""--sql
CREATE TABLE IF NOT EXISTS users (
    `phone` VARCHAR(11) PRIMARY KEY,
    -- 如果没有密码，则只能验证码登录
    `password` VARCHAR(100),
    -- 用json存储cookies
    -- json格式为playwright使用的cookie字典格式
    -- 这里本来用的是TEXT类型存储cookies，但是由于两个域名用的是不同的cookie
    -- TEXT存储字符串形式的cookies无法区分谁是那个域名的。
    -- 更何况JSON也更易读些。
    -- 具体的字段名与含义可以参考playwright._impl._api_structures.SetCookieParam
    -- 以及playwright._impl._api_structures.Cookie
    `cookies` JSON DEFAULT '[]'
);
""")
async def create_table(sql: str, conn: Connection) -> None:
    await conn.execute(sql)
    await conn.commit()


class User(BaseModel):
    phone: Annt[str, Field(pattern=r'^1[3-9]\d{9}$')]
    password: str | None = None
    cookies: list[Cookie] = []


@relate_sql("""--sql
INSERT
INTO users (`phone`, `password`, `cookies`)
VALUES (?, ?, json(?));
""")
async def insert_user(sql: str, conn: Connection, user: User | str | int) -> bool:
    if isinstance(user, (str, int)):
        user = User(phone=str(user))
    cur = await conn.execute(sql, (user.phone, user.password, json.dumps(user.cookies)))
    await conn.commit()
    return cur.rowcount == 1


@relate_sql("""--sql
UPDATE users
SET `cookies` = json(?)
WHERE `phone` = ?;
""")
async def update_cookies(sql: str, conn: Connection, phone: str | int, cookies: list[Cookie]) -> bool:
    cur = await conn.execute(sql, (json.dumps(cookies), phone))
    await conn.commit()
    return cur.rowcount == 1


@relate_sql("""--sql
SELECT `password` FROM users WHERE `phone` = ?;
""")
async def user_pwd(sql: str, conn: Connection, phone: str | int) -> str | None:
    cur = await conn.execute(sql, (phone,))
    row = await cur.fetchone()
    return row[0] if row else None


# TODO: get_user(phone: str | int)  all_users()


@relate_sql("""--sql
SELECT `phone`, `password`, `cookies` FROM users;
""")
async def all_users(sql, conn: Connection) -> list[User]:
    cur = await conn.execute(sql)
    rows = await cur.fetchall()
    return [User(
        phone=row[0],
        password=row[1],
        cookies=json.loads(row[2])
    ) for row in rows]
