from typing import Awaitable, Callable, Concatenate
from functools import wraps


def relate_sql[**P, R](sql: str) -> Callable[
    [Callable[Concatenate[str, P], Awaitable[R]]],
    Callable[Concatenate[P], Awaitable[R]]
]:
    """
    把sql语句和对应的dao层函数关联起来

    这样读代码的时候更易读，虽然会影响运行效率，但是个人觉得可读性更重要，毕竟你都已经用python了

    该函数返回的装饰器会把sql语句注入到原本函数的参数中

    为了可读性，建议把需要动态注入的参数填到`/`的右边，这样可以让函数签名更清晰

    :param sql: sql语句
    :return: 装饰器

    Example:
    ```python
    @relate_sql(
        sql = "SELECT * FROM user WHERE id = ?"
    )
    async def get_user(conn: Connection, user_id: int, /, sql: str) -> User:
        await conn.execute(sql, (user_id,))
        row = await conn.fetchone()
        return User(**row)
    """
    def deco(func: Callable[Concatenate[str, P], Awaitable[R]]):
        setattr(func, '__sql__', sql)
        @wraps(func)
        async def wrapper(*args, **kwargs):
            sql = getattr(func, '__sql__', '')
            args = (sql, *args)
            return await func(*args, **kwargs)
        return wrapper
    return deco


@relate_sql("SELECT * FROM user WHERE id = ?")
async def get_user(sql: str, /, a: str) -> None:
    print(sql)
    # 输出： "SELECT * FROM user WHERE id = ?"