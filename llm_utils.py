import asyncio
from copy import deepcopy
from logging import getLogger, INFO, basicConfig

from openai import AsyncOpenAI
import yaml

from dao.article import Article



SEM = asyncio.Semaphore(8)  # 限制并发量
CONFIG = yaml.safe_load(open("llm_config.yaml", "r", encoding="utf-8"))

LOGGER = getLogger(__name__)
basicConfig(level=INFO)



CLIENT = AsyncOpenAI(
    api_key=CONFIG['api_key'],
    base_url=CONFIG['base_url']
)


async def _llm_rewrite(content: str, prompt: str) -> str:
    try:
        # 异步调用聊天完成接口
        async with SEM:
            LOGGER.info(f"开始调用 LLM Rewrite API 进行洗稿：{content[:20]}……{content[-20:]}")
            completion = await CLIENT.chat.completions.create(
                model=CONFIG['model'],  # 指定豆包1.6 Flash模型
                messages=[
                    {
                        "role": "user",
                        "content": prompt+content
                    }
                ],
                temperature=0.7,  # 生成内容随机性，兼顾流畅度和多样性
                max_tokens=4096  # 提高令牌数，适配较长文章洗稿
            )
        
        # 提取并返回洗稿后的内容
        ans = completion.choices[0].message.content
        if ans is None:
            return ""
        # print(f"=== 待洗稿原文 ===\n{content}\n=== 待洗稿结果 ===\n{ans}")
        return ans.strip()
    except Exception as e:
        return f"洗稿调用失败：{str(e)}"


REWRITE_CONTENT_PROMPT = """
请你完成以下文章的洗稿工作，要求如下：
1.  核心主旨和关键信息完全保留，不增减原文的核心观点和重要数据；
2.  行文结构可适当调整，语句表达重新组织，避免与原文重复率过高；
3.  语言流畅、逻辑清晰，符合书面语规范，保持与原文相近的文风（正式/通俗）；
4.  无语法错误，无冗余内容，篇幅与原文大致相当（误差不超过 10%）。
5.  不需要对你的分析做出任何解释，直接返回洗稿后的结果

需要洗稿的原文：
"""


async def llm_rewrite_content(content: str) -> str:
    """
    异步调用豆包 1.6 Flash 版本完成文章洗稿（LLM Rewrite）

    :param content: 需要洗稿的原文内容
    :return: 洗稿后的改写文章
    """
    return await _llm_rewrite(content, REWRITE_CONTENT_PROMPT)


REWRITE_TITLE_PROMPT = """
请你完成以下标题的洗稿工作，要求如下：
1.  核心主旨和关键信息完全保留，不增减原标题的核心观点和重要数据；
2.  标题结构可适当调整，语句表达重新组织，避免与原标题重复率过高；
3.  语言流畅、逻辑清晰，符合书面语规范，保持与原标题相近的文风（正式/通俗）；
4.  不需要对你的分析做出任何解释，直接返回洗稿后的结果

需要洗稿的标题：
"""


async def llm_rewrite_title(title: str) -> str:
    """
    异步调用豆包 1.6 Flash 版本完成标题洗稿（LLM Rewrite）

    :param client: AsyncOpenAI 异步客户端实例（形参传入）
    :param title: 需要洗稿的标题内容
    :return: 洗稿后的改写标题
    """
    return await _llm_rewrite(title, REWRITE_TITLE_PROMPT)


async def llm_rewrite_article(
    article: Article,
    rewrite_content: bool = True,
    rewrite_title: bool = True,
) -> Article:
    '''
    调用llm洗稿文章标题与正文

    :param article: 待洗稿的文章对象
    :param rewrite_content: 是否需要洗稿文章正文
    :param rewrite_title: 是否需要洗稿文章标题
    :return: 洗稿后的文章对象
    '''
    if not rewrite_content and not rewrite_title:
        LOGGER.warning("未指定需要洗稿的文章内容，请检查参数")
        return article
    tasks = []
    if rewrite_content:
        tasks.append(llm_rewrite_content(article.content))
    if rewrite_title:
        tasks.append(llm_rewrite_title(article.title))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    content = ''
    title = ''
    if rewrite_content and not rewrite_title:
        if not isinstance(results[0], str):
            LOGGER.error(f"洗稿文章正文失败：{results[0]}")
            return article
        content = results[0]
    elif rewrite_title and not rewrite_content:
        if not isinstance(results[0], str):
            LOGGER.error(f"洗稿文章标题失败：{results[0]}")
            return article
        title = results[0]
    else:
        if not isinstance(results[0], str):
            LOGGER.error(f"洗稿文章正文失败：{results[0]}")
        else:
            content = results[0]
        if not isinstance(results[1], str):
            LOGGER.error(f"洗稿文章标题失败：{results[1]}")
        else:
            title = results[1]
    ans = deepcopy(article)
    ans.content = content if len(content) else article.content
    ans.title = title if len(title) else article.title
    return ans


# 异步主函数（用于测试）
async def main():
    # 1. 加载 YAML 配置
    # 2. 初始化 AsyncOpenAI 客户端（基于 YAML 配置）
    title = '玩原神救了我一命，我因此打败了抑郁症'
    content = '原神是一款充满奇妙魔法的游戏，玩家可以与神秘的怪物战斗，获得各种道具，打败怪物并收集各种材料，最终获得胜利。但玩家也会因为各种原因陷入抑郁症，导致无法正常游戏。'
    article = Article(title=title, content=content, id='1234567890', category='游戏', keyword='原神', url='https://www.bilibili.com/video/BV1xK411H74y')
    article = await llm_rewrite_article(article, rewrite_content=True, rewrite_title=True)
    print(article.title)
    print(article.content)


# 启动异步程序
if __name__ == "__main__":
    asyncio.run(main())