from typing import Annotated as Annt
from typing import Sequence

from pydantic import BaseModel, Field
import aiosqlite
from aiosqlite import Connection

from dao.dao_utils import relate_sql


@relate_sql("""--sql
CREATE TABLE IF NOT EXISTS users (
    `phone` VARCHAR(11) PRIMARY KEY,
    `password` VARCHAR(100),  -- 如果没有密码，则只能验证码登录
    `cookies` TEXT -- raw cookie string, nullable
);
""")
async def create_table(sql: str, conn: Connection) -> None:
    await conn.execute(sql)
    await conn.commit()


class User(BaseModel):
    phone: Annt[str, Field(pattern=r'^1[3-9]\d{9}$')]
    password: str | None = None
    cookies: str | None = None


@relate_sql("""--sql
INSERT INTO users (`phone`, `password`, `cookies`) VALUES (?,?,?);
""")
async def insert_user(sql: str, conn: Connection, user: User | str | int) -> bool:
    if isinstance(user, (str, int)):
        user = User(phone=str(user))
    cur = await conn.execute(sql, (user.phone, user.password, user.cookies))
    await conn.commit()
    return cur.rowcount == 1


@relate_sql("""--sql
UPDATE users SET `cookies` =? WHERE `phone` = ?;
""")
async def update_cookies(sql: str, conn: Connection, phone: str | int, cookies: str) -> bool:
    cur = await conn.execute(sql, (cookies, phone))
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
        cookies=row[2]
    ) for row in rows]
