"""
钉钉文档管理模块（用户面向）

用户只需传文档名、URL、行号、Sheet名等人类可读的参数，无需接触任何 ID。

使用示例:

    from ding_doc import DingTalkDoc
    dt = DingTalkDoc()

    # 列出我的文档
    files = dt.list_files()
    for f in files:
        print(f["name"], f["url"])

    # 通过链接读表格
    data = dt.read_xlsx("https://alidocs.dingtalk.com/i/nodes/xxxx")

    # 通过文档名读文档
    text = dt.read_doc("周报")

    # 创建文档并写入
    url = dt.create_doc("周报")
    dt.write_doc(url, "# 周报\\n本周完成...")

    # 往表格追加行
    dt.append_xlsx_rows("https://alidocs.dingtalk.com/i/nodes/xxxx",
                   [["张三", "技术部", "2024-01-15"]])

    # 修改文档第3段
    dt.update_paragraph("https://alidocs.dingtalk.com/i/nodes/xxxx", 2, "新内容")

    # 删除文档第1段
    dt.delete_paragraph("https://alidocs.dingtalk.com/i/nodes/xxxx", 0)

    # 查自己的 unionId
    print(dt.get_union_id(userid="20180223"))
"""

import os
from pathlib import Path
import dotenv
from ding_api import DingTalkAPI, DingTalkAPIError

dotenv.load_dotenv(Path(__file__).resolve().parent / ".env")


class DingTalkDoc:
    """
    钉钉文档管理客户端

    初始化:
        dt = DingTalkDoc()                          # 从 .env 读凭证
        dt = DingTalkDoc(app_key="xxx", app_secret="xxx", operator_id="xxx")
    """

    def __init__(self, app_key=None, app_secret=None, operator_id=None):
        self.api = DingTalkAPI(app_key, app_secret, operator_id)
        self._workspaces = None

    # ── 内部工具 ───────────────────────────────────────────

    def _get_workspace_id(self, workspace_name=None):
        """通过名称找 workspaceId，None=第一个"""
        if not self._workspaces:
            self._workspaces = self.list_workspaces()
        if not self._workspaces:
            raise ValueError("未找到知识库")
        if not workspace_name:
            return self._workspaces[0]["workspaceId"]
        for ws in self._workspaces:
            if ws.get("name") == workspace_name:
                return ws["workspaceId"]
        raise ValueError(f"未找到知识库: {workspace_name}")

    def _get_root_node_id(self, workspace_id):
        """通过 workspaceId 找 rootNodeId"""
        if not self._workspaces:
            self._workspaces = self.list_workspaces()
        for ws in self._workspaces:
            if ws.get("workspaceId") == workspace_id:
                return ws.get("rootNodeId")
        return None

    def _resolve_sheet_id(self, url_or_id, sheet_name=None):
        """通过 Sheet 名找 sheetId，None=第一个"""
        if not sheet_name:
            sheets = self.list_xlsx_sheets(url_or_id)
            if not sheets:
                raise ValueError("xlsx 中没有 sheet")
            return sheets[0]["id"]
        for s in self.list_xlsx_sheets(url_or_id):
            if s["name"] == sheet_name:
                return s["id"]
        raise ValueError(f"未找到 sheet: {sheet_name}")

    def _resolve_doc_key(self, url_or_name):
        """
        把 URL 或文档名解析成 docKey。
        - 如果是 URL 或 ID（含 nodes/ 或长度像 ID），直接提取
        - 否则按文档名在知识库里搜
        """
        if "nodes/" in url_or_name or len(url_or_name) > 20:
            return self.api.extract_node_id(url_or_name)
        file = self.find_file(url_or_name)
        if not file:
            raise ValueError(f"未找到文档: {url_or_name}")
        return file["nodeId"]

    # ── 浏览 ───────────────────────────────────────────────

    def list_workspaces(self):
        """
        列出我的知识库。

        返回: list[dict]:
            [{"name":"mine space", "workspaceId":"...", "rootNodeId":"..."}]
        """
        data = self.api.list_workspaces()
        ws = data.get("workspace")
        return [ws] if ws else data.get("workspaces", [])

    def list_files(self, workspace_name=None):
        """
        列出知识库下的所有文件（包含文档、表格、脑图等）。

        参数:
            workspace_name: 知识库名称，None=第一个

        返回: list[dict]:
            [{"name":"周报.adoc", "extension":"adoc", "url":"...", "nodeId":"...", ...}]
        """
        ws_id = self._get_workspace_id(workspace_name)
        root_id = self._get_root_node_id(ws_id)
        data = self.api.list_nodes(ws_id, root_id)
        return data.get("nodes", [])

    def find_file(self, name, workspace_name=None):
        """
        按名称查找文件（模糊匹配，跨文档/表格/脑图）。

        参数:
            name:           文件名（支持部分匹配）
            workspace_name: 知识库名称，None=第一个

        返回: dict 或 None:
            {"name":"...", "url":"...", "nodeId":"...", "extension":"..."}
        """
        for file in self.list_files(workspace_name):
            if name in file.get("name", ""):
                return file
        return None

    def get_file_info(self, url_or_name):
        """
        获取文件元信息（文档、表格、脑图均可）。

        参数:
            url_or_name: 文件 URL 或文件名

        返回: dict:
            {"name":"...", "extension":"...", "url":"...", "workspaceId":"..."}
        """
        if "nodes/" in url_or_name or len(url_or_name) > 20:
            return self.api.get_node(url_or_name).get("node", {})
        file = self.find_file(url_or_name)
        return file or {}

    # ── 文档：创建 ─────────────────────────────────────────

    def create_doc(self, name, workspace_name=None):
        """
        创建文字文档。

        参数:
            name:           文档名称
            workspace_name: 知识库名称，None=第一个

        返回: dict:
            {"url":"https://alidocs.dingtalk.com/i/nodes/xxx", "docKey":"...", ...}
        """
        ws_id = self._get_workspace_id(workspace_name)
        return self.api.create_doc(ws_id, name, "DOC")

    def create_xlsx(self, name, workspace_name=None):
        """
        创建表格（xlsx 文件）。

        参数:
            name:           表格名称
            workspace_name: 知识库名称，None=第一个

        返回: dict:
            {"url":"https://alidocs.dingtalk.com/i/nodes/xxx", "docKey":"...", ...}
        """
        ws_id = self._get_workspace_id(workspace_name)
        return self.api.create_doc(ws_id, name, "WORKBOOK")

    # ── 文档：读 ───────────────────────────────────────────

    def read_doc(self, url_or_name):
        """
        读取文档纯文本。

        参数:
            url_or_name: 文档 URL 或文档名

        返回: str，文档全文
        """
        doc_key = self._resolve_doc_key(url_or_name)
        data = self.api.get_doc_blocks(doc_key)
        blocks = data.get("data", [])
        lines = []
        for b in blocks:
            bt = b.get("blockType", "")
            elem = b.get(bt, {}) if bt else {}
            text = elem.get("text", "") if isinstance(elem, dict) else ""
            lines.append(text)
        return "\n".join(lines)

    def get_blocks(self, url_or_name):
        """
        获取文档段落列表（人类可读格式）。

        参数:
            url_or_name: 文档 URL 或文档名

        返回: list[dict]:
            [{"index":0, "type":"paragraph", "text":"第一段内容"},
             {"index":1, "type":"heading", "text":"标题"}]
        """
        doc_key = self._resolve_doc_key(url_or_name)
        data = self.api.get_doc_blocks(doc_key)
        blocks = data.get("data", [])
        result = []
        for i, b in enumerate(blocks):
            bt = b.get("blockType", "")
            elem = b.get(bt, {}) if bt else {}
            text = elem.get("text", "") if isinstance(elem, dict) else ""
            result.append({"index": i, "type": bt, "text": text})
        return result

    # ── 文档：写 ───────────────────────────────────────────

    def write_doc(self, url_or_name, markdown_content):
        """
        覆写文档（Markdown，原有内容被替换）。

        参数:
            url_or_name:        文档 URL 或文档名
            markdown_content:   Markdown 字符串

        返回: {"success": true}
        """
        doc_key = self._resolve_doc_key(url_or_name)
        return self.api.overwrite_content(doc_key, markdown_content)

    def append_doc(self, url_or_name, markdown_content):
        """
        在文档末尾追加内容（不影响原文）。

        参数:
            url_or_name:        文档 URL 或文档名
            markdown_content:   Markdown 字符串

        返回: {"success": true}
        """
        existing = self.read_doc(url_or_name)
        doc_key = self._resolve_doc_key(url_or_name)
        combined = existing + "\n\n" + markdown_content if existing else markdown_content
        return self.api.overwrite_content(doc_key, combined)

    def insert_paragraph(self, url_or_name, text, position=None):
        """
        在文档指定位置插入一个段落。

        参数:
            url_or_name: 文档 URL 或文档名
            text:        段落文本
            position:    插入位置（第几段，从0开始），None=末尾

        返回: API 响应
        """
        doc_key = self._resolve_doc_key(url_or_name)
        element = {"blockType": "paragraph", "paragraph": {"text": text}}
        return self.api.insert_block(doc_key, element, index=position)

    def update_paragraph(self, url_or_name, position, text):
        """
        修改文档指定段落的文本。

        参数:
            url_or_name: 文档 URL 或文档名
            position:    第几段（从0开始）
            text:        新文本

        返回: API 响应
        """
        doc_key = self._resolve_doc_key(url_or_name)
        blocks = self.api.get_doc_blocks(doc_key).get("data", [])
        if position < 0 or position >= len(blocks):
            raise ValueError(f"位置超出范围: 文档共 {len(blocks)} 段，position={position}")
        block_id = blocks[position].get("blockId")
        element = {"blockType": "paragraph", "paragraph": {"text": text}}
        return self.api.update_block(doc_key, block_id, element)

    def delete_paragraph(self, url_or_name, position):
        """
        删除文档指定段落。

        参数:
            url_or_name: 文档 URL 或文档名
            position:    第几段（从0开始）

        返回: API 响应
        """
        doc_key = self._resolve_doc_key(url_or_name)
        blocks = self.api.get_doc_blocks(doc_key).get("data", [])
        if position < 0 or position >= len(blocks):
            raise ValueError(f"位置超出范围: 文档共 {len(blocks)} 段，position={position}")
        block_id = blocks[position].get("blockId")
        return self.api.delete_block(doc_key, block_id)

    # ── 表格：读 ───────────────────────────────────────────

    def read_xlsx(self, url_or_name, cell_range="A1:Z1000", sheet_name=None):
        """
        读取 xlsx 表格数据。

        参数:
            url_or_name: xlsx URL 或文档名
            cell_range:  读取区域，默认 "A1:Z1000"
            sheet_name:  sheet 页名称，None=第一个

        返回: list[list[str]]:
            [["姓名","部门"], ["张三","技术部"]]
        """
        doc_key = self._resolve_doc_key(url_or_name)
        sheet_id = self._resolve_sheet_id(doc_key, sheet_name)
        return self.api.read_range(doc_key, sheet_id, cell_range).get("displayValues", [])

    def list_xlsx_sheets(self, url_or_name):
        """
        列出 xlsx 中的所有 sheet 页。

        参数:
            url_or_name: xlsx URL 或文档名

        返回: list[dict]:
            [{"name":"Sheet1", "id":"xxx"}, ...]
        """
        doc_key = self._resolve_doc_key(url_or_name)
        return self.api.list_sheets(doc_key).get("value", [])

    # ── 表格：写 ───────────────────────────────────────────

    def write_xlsx(self, url_or_name, cell_range, values, sheet_name=None):
        """
        写入 xlsx 表格区域（覆盖写入）。

        参数:
            url_or_name: xlsx URL 或文档名
            cell_range:  目标区域，如 "A1:C3"
            values:      二维数组，如 [["a","b"],["c","d"]]
            sheet_name:  sheet 页名称，None=第一个

        返回: API 响应
        """
        doc_key = self._resolve_doc_key(url_or_name)
        sheet_id = self._resolve_sheet_id(doc_key, sheet_name)
        return self.api.write_range(doc_key, sheet_id, cell_range, values)

    def append_xlsx_rows(self, url_or_name, rows, sheet_name=None):
        """
        向 xlsx 表格追加行（自动定位最后一行之后，不覆盖已有数据）。

        参数:
            url_or_name: xlsx URL 或文档名
            rows:        二维数组，如 [["张三","技术部","2024-01-15"]]
            sheet_name:  sheet 页名称，None=第一个

        返回: API 响应
        """
        doc_key = self._resolve_doc_key(url_or_name)
        sheet_id = self._resolve_sheet_id(doc_key, sheet_name)
        existing = self.api.read_range(doc_key, sheet_id, "A1:Z1000").get("displayValues", [])
        last_row = 0
        for i, row in enumerate(existing):
            if any(cell.strip() for cell in row if isinstance(cell, str)):
                last_row = i + 1
        start = last_row + 1
        col_count = max(len(r) for r in rows) if rows else 1
        end_col = chr(ord("A") + col_count - 1)
        cell_range = f"A{start}:{end_col}{start + len(rows) - 1}"
        return self.api.write_range(doc_key, sheet_id, cell_range, rows)

    # ── 用户 ───────────────────────────────────────────────

    def get_union_id(self, userid=None, mobile=None):
        """
        获取 unionId。

        参数:
            userid: 工号（员工账号）
            mobile: 手机号
            传一个即可

        返回: str
        """
        return self.get_user_info(userid, mobile).get("unionid")

    def get_user_info(self, userid=None, mobile=None):
        """
        获取用户完整信息。

        参数:
            userid: 工号
            mobile: 手机号

        返回: dict:
            {"name":"...", "userid":"...", "unionid":"...", "title":"..."}
        """
        if userid:
            data = self.api.get_user_by_userid(userid)
        elif mobile:
            data = self.api.get_user_by_mobile(mobile)
        else:
            raise ValueError("需要 userid 或 mobile")
        if data.get("errcode") != 0:
            raise DingTalkAPIError(data.get("errcode"), data.get("errmsg"))
        return data.get("result", {})
