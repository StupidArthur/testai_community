"""ai_service 异常类型。"""


class LLMError(Exception):
    """LLM 调用失败。"""


class LLMNotConfiguredError(LLMError):
    """未配置 MINIMAX_API_KEY 等必要环境变量。"""


class TavilyNotConfiguredError(Exception):
    """未配置 TAVILY_API_KEY。"""


class NewsSearchError(Exception):
    """Tavily 搜索失败或返回异常。"""
