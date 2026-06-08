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

SECTION_ORDER = [
    "role", "profile", "background", "goals", "constraints",
    "core_skills", "workflows", "output_format", "initialization",
]

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


def parse_langgpt_to_fields(payload: str) -> dict[str, str]:
    result = {key: "" for key in SECTION_ORDER}
    if not payload:
        return result

    current_section = None
    for line in payload.split("\n"):
        stripped = line.strip()
        matched = False
        for marker, key in SECTION_MAP.items():
            if stripped.startswith(marker):
                current_section = key
                if key == "role":
                    prefix = marker
                    role_value = stripped[len(prefix):].strip()
                    result["role"] = role_value
                matched = True
                break
        if matched:
            continue
        if current_section and current_section != "role":
            result[current_section] += stripped + "\n"

    for key in result:
        if key != "role":
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