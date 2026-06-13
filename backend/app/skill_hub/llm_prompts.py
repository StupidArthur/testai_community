"""skill_hub 侧 LLM 提示词与 messages 组装（业务 prompt 不归 ai_service）。"""

from __future__ import annotations

# evaluate-draft 评审专家 system prompt
EVALUATE_DRAFT_SYSTEM = (
    "你是一个 LangGPT Prompt 评审专家。请基于以下 9 维 LangGPT 规范的旧版本与新草稿，"
    "输出三段内容（用中文，Markdown 格式）：\n\n"
    "1. 【diff_summary】用 3-5 个 bullet 简明扼要总结新旧版本在结构与内容上的实质性变化。\n\n"
    "2. 【evaluation】客观评估新草稿的合规性与质量：是否覆盖了 Role/Profile/Background/Goals/"
    "Constraints/Core Skills/Workflows/Output Format/Initialization 这 9 个维度；"
    "Constraints 是否使用强硬祈使句；Workflows 是否为有序 SOP；"
    "Core Skills 是否给出具体实现逻辑而非空泛名字。\n\n"
    "3. 【suggestions】给出 3-5 条具体的可执行改进建议。\n\n"
    "输出格式严格按以下结构（用 --- 分隔三段，不要多余前言）：\n"
    "---\n"
    "【diff_summary】\n<内容>\n"
    "---\n"
    "【evaluation】\n<内容>\n"
    "---\n"
    "【suggestions】\n<内容>\n"
)


def build_commit_diff_messages(old_payload: str, new_payload: str) -> list[dict[str, str]]:
    """版本保存时生成 ai_commit_summary 的 messages。"""
    content = (
        f"旧版本提示词：{old_payload}\n\n"
        f"新版本提示词：{new_payload}\n\n"
        "请用3个简短的Markdown列表项，总结业务逻辑和规则方面的实质性改变。"
    )
    return [{"role": "user", "content": content}]


def build_evaluate_draft_messages(old_payload: str, new_payload: str) -> list[dict[str, str]]:
    """沙箱 evaluate-draft 预评估的 messages。"""
    user_prompt = f"【旧版本】\n{old_payload}\n\n【新草稿】\n{new_payload}"
    return [
        {"role": "system", "content": EVALUATE_DRAFT_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
