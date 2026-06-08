import httpx

from app.core.config import MINIMAX_API_KEY, MINIMAX_API_URL


async def call_minimax(messages: list[dict], temperature: float = 0.3) -> str:
    if not MINIMAX_API_KEY:
        return "[LLM未配置] 请设置环境变量 MINIMAX_API_KEY"

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-M2.7-highspeed",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(MINIMAX_API_URL, json=payload, headers=headers)
        if response.status_code != 200:
            return f"[LLM错误] HTTP {response.status_code}: {response.text[:500]}"
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "[LLM返回为空]")


async def run_prompt(prompt: str, mock_input: str) -> str:
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": mock_input},
    ]
    return await call_minimax(messages, temperature=0.7)


async def lint_prompt(langgpt_payload: str) -> str:
    system_prompt = """你是一个 LangGPT 格式审查助手。请检查以下 Prompt 是否符合 LangGPT 规范。

规范要求：
1. 必须有 # Role 部分定义角色名称
2. 必须有 ## Profile 部分包含 Author, Version, Language, Description
3. 必须有 ## Rules 部分列出行为规则
4. 必须有 ## Workflow 部分描述工作流程
5. 必须有 ## Initialization 部分定义初始化行为

请以 Markdown 列表形式输出审查结果，指出问题和改进建议。如果没有问题，回复"格式规范，无需修改"."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请审查以下 Prompt：\n\n{langgpt_payload}"},
    ]
    return await call_minimax(messages, temperature=0.2)


async def semantic_diff(old_payload: str, new_payload: str) -> str:
    prompt = f"旧版本提示词：{old_payload}\n\n新版本提示词：{new_payload}\n\n请用3个简短的Markdown列表项，总结业务逻辑和规则方面的实质性改变。"
    messages = [
        {"role": "user", "content": prompt},
    ]
    return await call_minimax(messages, temperature=0.3)