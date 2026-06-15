"""skill_hub 九维 payload 解析/组装单元测试。"""

from app.skill_hub.utils import dimensions_to_payload, payload_to_dimensions


class TestSkillPayloadUtils:
    def test_roundtrip(self):
        dims = {
            "role": "资深测试专家",
            "profile": "- Author: QA",
            "background": "业务背景",
            "goals": "1. 生成用例",
            "constraints": "必须完整",
            "core_skills": "解析 OpenAPI",
            "workflows": "1. 解析\n2. 输出",
            "output_format": "Markdown 表格",
            "initialization": "准备好了",
        }
        payload = dimensions_to_payload(**dims)
        parsed = payload_to_dimensions(payload)
        for key, value in dims.items():
            assert parsed[key] == value

    def test_empty_payload(self):
        parsed = payload_to_dimensions("")
        assert all(v == "" for v in parsed.values())
