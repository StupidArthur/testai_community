"""
python-docx 兼容：跳过损坏的 Relationship（Target=NULL / 内部书签 #xxx）。

部分 Word 文档（图片超链接到书签、损坏的 rels）在 Document() 加载时会抛出：
  KeyError: "There is no item named 'NULL' in the archive"
本模块在首次加载前打补丁，避免整篇文档无法解析。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_PATCHED = False


def ensure_docx_broken_rels_patch() -> None:
    """幂等打补丁：加载 .rels 时跳过无效 Target。"""
    global _PATCHED
    if _PATCHED:
        return
    try:
        from docx.opc.oxml import parse_xml
        from docx.opc.pkgreader import _SerializedRelationship, _SerializedRelationships
    except Exception as exc:  # noqa: BLE001
        log.warning("docx compat patch skipped: %s", exc)
        return

    def load_from_xml_safe(baseURI, rels_item_xml):  # noqa: N803 — 对齐上游签名
        srels = _SerializedRelationships()
        if rels_item_xml is None:
            return srels
        rels_elm = parse_xml(rels_item_xml)
        for rel_elm in rels_elm.Relationship_lst:
            target = (getattr(rel_elm, "target_ref", None) or "").strip()
            # NULL / ../NULL：损坏图片链；#…：内部书签，不是包内 part
            if (
                not target
                or target.upper() == "NULL"
                or target.upper().endswith("/NULL")
                or target.startswith("#")
            ):
                continue
            srels._srels.append(_SerializedRelationship(baseURI, rel_elm))
        return srels

    _SerializedRelationships.load_from_xml = load_from_xml_safe  # type: ignore[method-assign]
    _PATCHED = True
    log.info("python-docx broken relationship patch applied")
