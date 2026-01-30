import asyncio
from logging import getLogger, INFO, basicConfig

from openai import AsyncOpenAI
import yaml
from aiosqlite import connect

from dao.article import all_articles



SEM = asyncio.Semaphore(3)  # 限制并发量为 3
CONFIG = yaml.safe_load(open("llm_config.yaml", "r", encoding="utf-8"))

LOGGER = getLogger(__name__)
basicConfig(level=INFO)

REWRITE_PROMPT = """
请你完成以下文章的洗稿工作，要求如下：
1.  核心主旨和关键信息完全保留，不增减原文的核心观点和重要数据；
2.  行文结构可适当调整，语句表达重新组织，避免与原文重复率过高；
3.  语言流畅、逻辑清晰，符合书面语规范，保持与原文相近的文风（正式/通俗）；
4.  无语法错误，无冗余内容，篇幅与原文大致相当（误差不超过 10%）。

需要洗稿的原文：
"""

CLIENT = AsyncOpenAI(
    api_key=CONFIG['api_key'],
    base_url=CONFIG['base_url']
)


async def llm_rewrite(article: str) -> str:
    """
    异步调用豆包 1.6 Flash 版本完成文章洗稿（LLM Rewrite）

    :param client: AsyncOpenAI 异步客户端实例（形参传入）
    :param article: 需要洗稿的原文内容
    :return: 洗稿后的改写文章
    """
    try:
        # 异步调用聊天完成接口
        async with SEM:
            LOGGER.info(f"开始调用 LLM Rewrite API 进行文章洗稿：{article[:20]}……{article[-20:]}")
            completion = await CLIENT.chat.completions.create(
                model=CONFIG['model'],  # 指定豆包1.6 Flash模型
                messages=[
                    {
                        "role": "user",
                        "content": REWRITE_PROMPT+article
                    }
                ],
                temperature=0.7,  # 生成内容随机性，兼顾流畅度和多样性
                max_tokens=4096  # 提高令牌数，适配较长文章洗稿
            )
        
        # 提取并返回洗稿后的内容
        ans = completion.choices[0].message.content
        if ans is None:
            return ""
        # print(f"=== 待洗稿原文 ===\n{article}\n=== 待洗稿结果 ===\n{ans}")
        return ans
    except Exception as e:
        return f"洗稿调用失败：{str(e)}"


# 异步主函数（用于测试）
async def main():
    # 1. 加载 YAML 配置
    # 2. 初始化 AsyncOpenAI 客户端（基于 YAML 配置）
    async with connect('data.db') as conn:
        articles = await all_articles(conn)

    articles = [
        article for article in articles
        if len(article.content)
    ]

    tasks = [
        llm_rewrite(article.content)
        for article in articles
    ]

    results = await asyncio.gather(*tasks)


# 启动异步程序
if __name__ == "__main__":
    asyncio.run(main())