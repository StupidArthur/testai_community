"""xlsx 文档解析单元测试。"""

from pathlib import Path

from openpyxl import Workbook

from app.ai_service.document.loaders import load_document_text_and_images


def test_read_xlsx(tmp_path: Path):
    xlsx_path = tmp_path / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws["A1"] = "名称"
    ws["B1"] = "值"
    ws["A2"] = "测试项"
    ws["B2"] = 42
    wb.save(xlsx_path)

    text, images, warnings = load_document_text_and_images(xlsx_path)
    assert "测试项" in text
    assert "42" in text
    assert images == []
