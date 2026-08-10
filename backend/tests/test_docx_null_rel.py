"""docx Target=NULL 损坏关系应可解析正文。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document

from app.ai_service.document.loaders import load_document_text_and_images


def _inject_null_image_rel(docx_path: Path) -> None:
    """在 document.xml.rels 中插入 Target=NULL 的图片关系，模拟损坏文档。"""
    buf = docx_path.read_bytes()
    tmp = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                xml = data.decode("utf-8")
                inject = (
                    '<Relationship Id="rIdNullBad" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    'Target="NULL"/>'
                )
                xml = xml.replace("</Relationships>", inject + "</Relationships>")
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(docx_path)


def test_docx_with_null_relationship_still_loads(tmp_path: Path):
    path = tmp_path / "broken_null.docx"
    doc = Document()
    doc.add_paragraph("损坏关系文档仍应读出这段正文。" * 5)
    doc.save(path)
    _inject_null_image_rel(path)

    text, _images, _warnings = load_document_text_and_images(path)
    assert "损坏关系文档仍应读出这段正文" in text
