SECTION_MAP = {
    "# Role": "role",
    "## Profile": "profile",
    "## Background": "background",
    "## Goals": "goals",
    "## Constraints": "constraints",
    "## Core Skills": "core_skills",
    "## Workflows": "workflows",
    "## Output Format": "output_format",
    "## Initialization": "initialization",
}

# 九维字段键名顺序（与 LangGPT 章节一一对应）
SECTION_ORDER = [
    "role", "profile", "background", "goals", "constraints",
    "core_skills", "workflows", "output_format", "initialization",
]

# 空九维字典，供解析兜底
EMPTY_DIMENSIONS: dict[str, str] = {key: "" for key in SECTION_ORDER}

SECTION_HEADERS = {
    "role": "# Role",
    "profile": "## Profile",
    "background": "## Background",
    "goals": "## Goals",
    "constraints": "## Constraints",
    "core_skills": "## Core Skills",
    "workflows": "## Workflows",
    "output_format": "## Output Format",
    "initialization": "## Initialization",
}


def payload_to_dimensions(payload: str) -> dict[str, str]:
    """将 LangGPT Markdown payload 解析为九维字典。"""
    return parse_langgpt_to_fields(payload)


def dimensions_to_payload(**kwargs: str) -> str:
    """将九维字段组装为 LangGPT Markdown payload（持久化唯一格式）。"""
    return fields_to_langgpt(
        role=kwargs.get("role", ""),
        profile=kwargs.get("profile", ""),
        background=kwargs.get("background", ""),
        goals=kwargs.get("goals", ""),
        constraints=kwargs.get("constraints", ""),
        core_skills=kwargs.get("core_skills", ""),
        workflows=kwargs.get("workflows", ""),
        output_format=kwargs.get("output_format", ""),
        initialization=kwargs.get("initialization", ""),
    )


def parse_langgpt_to_fields(payload: str) -> dict[str, str]:
    """解析 LangGPT Markdown；章节标题可与内容同行，也可在下一行起续写。"""
    result = dict(EMPTY_DIMENSIONS)
    if not payload:
        return result

    current_section: str | None = None
    for line in payload.split("\n"):
        stripped = line.strip()
        matched = False
        for marker, key in SECTION_MAP.items():
            if stripped.startswith(marker):
                current_section = key
                inline = stripped[len(marker):].strip()
                if inline:
                    result[key] = inline + "\n"
                matched = True
                break
        if matched:
            continue
        if current_section:
            result[current_section] += stripped + "\n"

    for key in result:
        result[key] = result[key].strip()
    return result


def fields_to_langgpt(
    role: str = "",
    profile: str = "",
    background: str = "",
    goals: str = "",
    constraints: str = "",
    core_skills: str = "",
    workflows: str = "",
    output_format: str = "",
    initialization: str = "",
) -> str:
    parts = [f"# Role\n{role}"]
    if profile:
        parts.append(f"\n## Profile\n{profile}")
    if background:
        parts.append(f"\n## Background\n{background}")
    if goals:
        parts.append(f"\n## Goals\n{goals}")
    if constraints:
        parts.append(f"\n## Constraints\n{constraints}")
    if core_skills:
        parts.append(f"\n## Core Skills\n{core_skills}")
    if workflows:
        parts.append(f"\n## Workflows\n{workflows}")
    if output_format:
        parts.append(f"\n## Output Format\n{output_format}")
    if initialization:
        parts.append(f"\n## Initialization\n{initialization}")
    return "\n".join(parts)