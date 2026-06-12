"""translate 模块单元测试：数据校验、预处理、XML 解析、zip 工具。不依赖 LLM API。"""

import json
import zipfile
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, SAMPLE_ZIP

from app.translate.validate import validate_recording
from app.translate.adapter import adapt_meta_v0_to_v1, adapt_action_v0_to_v1, parse_desc
from app.translate.xml_parse import preprocess_llm_xml_output, _strip_fence, parse_steps_xml
from app.translate.zip_utils import safe_extract
from app.translate.models import RecordingMeta, RawAction, ElementInfo
from app.translate.preprocess.classify import classify_action
from app.translate.preprocess.noise import detect_noise
from app.translate.preprocess.diff import compute_all_diffs
from app.translate.preprocess.merge import merge_actions
from app.translate.preprocess.form_state import compute_form_state_changes, format_form_state_changes
from app.translate.result_zip import RESULT_WHITELIST, create_result_zip


class TestAdapter:
    def test_parse_desc_click(self):
        result = parse_desc('点击 <input> "请输入用户名"')
        assert result["tag"] == "input"
        assert result["desc"] == "请输入用户名"

    def test_parse_desc_no_tag(self):
        result = parse_desc("按键 Enter")
        assert result["tag"] == ""
        assert result["desc"] == "按键 Enter"

    def test_adapt_meta_v0(self):
        raw = {
            "recordStartTime": "2026-06-10T10:00:00.000Z",
            "recordEndTime": "2026-06-10T10:00:15.000Z",
            "totalActions": 5,
            "targetUrl": "https://example.com",
            "startPageTitle": "Test",
            "snapshotPollIntervalMs": 300,
            "convention": "action_N: pre=snapshot_{N-1}",
            "actionSummary": [
                {"index": 1, "type": "click", "desc": '点击 <button> "登录"', "page": "Test"}
            ],
        }
        adapted = adapt_meta_v0_to_v1(raw)
        assert adapted["formatVersion"] == "0.0"
        assert adapted["totalSnapshots"] == 6
        assert "convention" not in adapted
        assert adapted["actionSummary"][0]["elementTag"] == "button"
        assert adapted["actionSummary"][0]["elementDesc"] == "登录"
        assert adapted["actionSummary"][0]["pageTitle"] == "Test"

    def test_adapt_action_v0(self):
        raw = {
            "index": 1,
            "type": "click",
            "title": "Test Page",
            "timestamp": 1000,
            "url": "https://example.com",
            "element": {"tag": "input", "xpath": "//*[@id='x']"},
            "formStateDelta": {"key": "val"},
        }
        adapted = adapt_action_v0_to_v1(raw)
        assert adapted["pageTitle"] == "Test Page"
        assert "title" not in adapted
        assert adapted["formState"] == {"key": "val"}
        assert "formStateDelta" not in adapted


class TestXmlParse:
    def test_strip_fence_markdown(self):
        raw = "```xml\n<steps><step id='1'/></steps>\n```"
        assert _strip_fence(raw) == "<steps><step id='1'/></steps>"

    def test_strip_fence_thinking(self):
        raw = "<think>some thought</think><steps/>"
        assert _strip_fence(raw) == "<steps/>"

    def test_strip_fence_thinking_tag(self):
        raw = "<thinking>deep thought</thinking><steps/>"
        assert _strip_fence(raw) == "<steps/>"

    def test_preprocess_bom(self):
        raw = "\ufeff<steps/>"
        text, truncated = preprocess_llm_xml_output(raw)
        assert text == "<steps/>"
        assert not truncated

    def test_preprocess_truncation(self):
        raw = "x" * 100
        text, truncated = preprocess_llm_xml_output(raw, max_chars=50)
        assert len(text) == 50
        assert truncated

    def test_parse_steps_xml_basic(self):
        xml = """<steps>
        <step id="1">
            <description>点击登录</description>
            <actionKind>click</actionKind>
            <target>button</target>
        </step>
        </steps>"""
        steps = parse_steps_xml(xml)
        assert len(steps) == 1
        assert steps[0]["id"] == 1

    def test_parse_steps_xml_auto_wrap(self):
        xml = '<step id="1"><description>test</description></step>'
        steps = parse_steps_xml(xml)
        assert len(steps) >= 1


class TestValidateRecording:
    def test_validate_sample(self):
        run_dir = FIXTURES_DIR / "sample_recording" / "run_2026-06-10T10-00-00"
        meta, raw_actions, version = validate_recording(run_dir)
        assert meta.total_actions == 5
        assert meta.total_snapshots == 6
        assert len(raw_actions) == 5
        assert raw_actions[0].type == "click"
        assert raw_actions[0].element.tag == "input"

    def test_validate_missing_meta(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_recording(tmp_path / "nonexistent")


class TestZipUtils:
    def test_safe_extract(self, tmp_path):
        assert SAMPLE_ZIP.exists()
        extract_dir = tmp_path / "extracted"
        run_dir = safe_extract(SAMPLE_ZIP, extract_dir)
        assert (run_dir / "meta.json").exists()
        assert (run_dir / "record" / "actions" / "action_001.json").exists()
        assert (run_dir / "record" / "snapshots" / "snapshot_000.txt").exists()

    def test_safe_extract_no_meta(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        with pytest.raises(ValueError, match="meta.json"):
            safe_extract(bad_zip, tmp_path / "extract")

    def test_path_traversal_defense(self, tmp_path):
        bad_zip = tmp_path / "evil.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../../../etc/passwd", "root:x:0:0")
            zf.writestr("meta.json", '{"totalActions":0}')
        extract_dir = tmp_path / "extract"
        run_dir = safe_extract(bad_zip, extract_dir)
        assert (run_dir / "meta.json").exists()
        assert not (extract_dir / "../../../etc/passwd").exists()


class TestPreprocess:
    @pytest.fixture()
    def sample_data(self):
        run_dir = FIXTURES_DIR / "sample_recording" / "run_2026-06-10T10-00-00"
        meta, raw_actions, _ = validate_recording(run_dir)
        return run_dir, meta, raw_actions

    def test_merge_actions(self, sample_data):
        _, _, raw_actions = sample_data
        merged, report = merge_actions(raw_actions)
        assert len(merged) > 0
        assert "dblclickDeduped" in report

    def test_compute_diffs(self, sample_data):
        run_dir, meta, _ = sample_data
        diffs = compute_all_diffs(run_dir, meta.total_snapshots)
        assert isinstance(diffs, dict)

    def test_classify_action(self):
        classification = classify_action(
            "click",
            ElementInfo(tag="button", text="登录", xpath="//button"),
            "无变化",
            {},
        )
        assert classification.category in ("navigation", "interaction", "form", "other")
        assert classification.element_type in ("button", "other")

    def test_detect_noise(self):
        from app.translate.models import EnrichedAction
        action = EnrichedAction(
            index=1,
            type="click",
            element=ElementInfo(tag="div", xpath="//div"),
            url="https://example.com",
            page_title="Test",
            timestamp=1000,
            snapshot_diff="无可见变化",
        )
        is_noise, reason = detect_noise(action, is_first=False, is_last=False)
        assert isinstance(is_noise, bool)

    def test_form_state_changes(self):
        prev = {"field1": {"value": "a"}, "field2": {"value": "b"}}
        curr = {"field1": {"value": "a"}, "field2": {"value": "c"}}
        changes = compute_form_state_changes(prev, curr)
        assert changes["hasChanges"] is True

    def test_form_state_no_changes(self):
        prev = {"field1": {"value": "a"}}
        curr = {"field1": {"value": "a"}}
        changes = compute_form_state_changes(prev, curr)
        assert changes["hasChanges"] is False

    def test_full_preprocess(self, sample_data):
        from app.translate.preprocess import preprocess
        run_dir, meta, raw_actions = sample_data
        enriched = preprocess(run_dir, meta, raw_actions)
        assert len(enriched) > 0
        assert all(e.index > 0 for e in enriched)


class TestResultZip:
    def test_create_result_zip(self, tmp_path):
        run_dir = tmp_path / "run"
        phase1_dir = run_dir / "translate" / "phase1"
        phase2_dir = run_dir / "translate" / "phase2"
        phase4_dir = run_dir / "translate" / "phase4"
        for d in (phase1_dir, phase2_dir, phase4_dir):
            d.mkdir(parents=True, exist_ok=True)

        (phase1_dir / "structured_steps.json").write_text("[]")
        (phase2_dir / "cases.md").write_text("# Cases")
        (phase4_dir / "agents.txt").write_text("agent1")

        out_path = tmp_path / "result.zip"
        create_result_zip(run_dir, out_path)
        assert out_path.exists()

        with zipfile.ZipFile(out_path) as zf:
            names = zf.namelist()
            assert "translate/phase1/structured_steps.json" in names
            assert "translate/phase2/cases.md" in names
            assert "translate/phase4/agents.txt" in names

    def test_whitelist_no_sensitive_files(self, tmp_path):
        run_dir = tmp_path / "run"
        sensitive_dir = run_dir / "translate" / "llm_audit"
        sensitive_dir.mkdir(parents=True, exist_ok=True)
        (sensitive_dir / "audit.log").write_text("sensitive data")

        out_path = tmp_path / "result.zip"
        create_result_zip(run_dir, out_path)

        with zipfile.ZipFile(out_path) as zf:
            names = zf.namelist()
            assert not any("llm_audit" in n for n in names)


class TestModels:
    def test_recording_meta_from_v0(self):
        raw = {
            "recordStartTime": "2026-06-10T10:00:00.000Z",
            "recordEndTime": "2026-06-10T10:00:15.000Z",
            "totalActions": 5,
            "totalSnapshots": 6,
            "targetUrl": "https://example.com",
            "startPageTitle": "Test",
            "snapshotPollIntervalMs": 300,
            "formatVersion": "1.0",
            "actionSummary": [
                {
                    "index": 1,
                    "type": "click",
                    "elementTag": "input",
                    "elementDesc": "username",
                    "pageTitle": "Test",
                }
            ],
        }
        meta = RecordingMeta.model_validate(raw)
        assert meta.total_actions == 5
        assert meta.total_snapshots == 6

    def test_raw_action_from_v1(self):
        raw = {
            "index": 1,
            "type": "click",
            "timestamp": 1000,
            "url": "https://example.com",
            "pageTitle": "Test",
            "element": {"tag": "button", "xpath": "//button"},
        }
        action = RawAction.model_validate(raw)
        assert action.type == "click"
        assert action.element.tag == "button"

    def test_element_info_defaults(self):
        el = ElementInfo(tag="div", xpath="//div")
        assert el.text == ""
        assert el.id is None
