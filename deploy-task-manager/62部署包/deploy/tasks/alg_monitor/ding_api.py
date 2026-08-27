"""
钉钉 OpenAPI 原始封装层

每个方法与钉钉开放平台 API 一一对应，不做额外封装。
上层模块 ding_doc.py 在此基础上提供面向用户的文档管理能力。

凭证获取：
  app_key / app_secret：开发者后台 -> 应用 -> 基础信息 -> 应用信息
  operator_id（unionId）：通过 get_union_id(userid="工号") 获取

环境变量（.env）：
  APP_KEY=dingxxxxxxxx
  APP_SECRET=xxxxxxxx
  OPERATOR_ID=xxxxxxxx
"""

import os
import re
import time
from pathlib import Path
import httpx
import dotenv

dotenv.load_dotenv(Path(__file__).resolve().parent / ".env")


class DingTalkAPIError(Exception):
    """钉钉 API 调用异常"""
    def __init__(self, code, message, response=None):
        self.code = code
        self.message = message
        self.response = response
        super().__init__(f"[{code}] {message}")


class DingTalkAPI:
    """
    钉钉 OpenAPI 客户端（1:1 原始封装）

    初始化:
        api = DingTalkAPI()                          # 从 .env 读凭证
        api = DingTalkAPI(app_key="xxx", app_secret="xxx", operator_id="xxx")

    所有方法与 API 一一对应，详见各方法 docstring 中的 HTTP / Path。
    """

    BASE = "https://api.dingtalk.com"
    OAPI = "https://oapi.dingtalk.com"

    def __init__(self, app_key=None, app_secret=None, operator_id=None):
        self.app_key = app_key or os.environ.get("APP_KEY")
        self.app_secret = app_secret or os.environ.get("APP_SECRET")
        self.operator_id = operator_id or os.environ.get("OPERATOR_ID")
        if not self.app_key or not self.app_secret:
            raise ValueError("需要 app_key/app_secret，可传参或设环境变量 APP_KEY/APP_SECRET")
        self._token = None
        self._token_expire = 0
        self._client = httpx.Client(timeout=30)

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass

    # ── 内部工具 ────────────────────────────────────────────

    def _get_token(self):
        """获取并缓存 accessToken（有效期 7200 秒，自动续期）"""
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        r = self._client.post(
            f"{self.BASE}/v1.0/oauth2/accessToken",
            json={"appKey": self.app_key, "appSecret": self.app_secret},
        )
        data = r.json()
        self._token = data["accessToken"]
        self._token_expire = time.time() + data.get("expireIn", 7200)
        return self._token

    def _headers(self):
        return {
            "x-acs-dingtalk-access-token": self._get_token(),
            "Content-Type": "application/json",
        }

    def _check(self, r):
        if r.status_code >= 400:
            try:
                data = r.json()
            except Exception:
                raise DingTalkAPIError(r.status_code, r.text, r)
            raise DingTalkAPIError(
                data.get("code", r.status_code),
                data.get("message", str(data)),
                r,
            )
        return r

    def _op(self, operator_id=None):
        """返回 operatorId，优先参数传入，其次构造时设的 operator_id"""
        op = operator_id or self.operator_id
        if not op:
            raise ValueError("需要 operatorId（unionId），可在构造时传入或设环境变量 OPERATOR_ID")
        return op

    @staticmethod
    def extract_node_id(url_or_id):
        """
        从 URL 或纯 ID 中提取 nodeId / dentryUuid。

        输入: "https://alidocs.dingtalk.com/i/nodes/Amq4xxx?utm_scene=person_space"
        返回: "Amq4xxx"
        """
        m = re.search(r"nodes/([A-Za-z0-9_-]+)", url_or_id)
        return m.group(1) if m else url_or_id.strip()

    # ── Token ──────────────────────────────────────────────

    def get_access_token(self):
        """
        获取企业内部应用 accessToken。

        API: POST /v1.0/oauth2/accessToken
        权限: 无

        返回: {"accessToken": "xxx", "expireIn": 7200}
        """
        r = self._client.post(
            f"{self.BASE}/v1.0/oauth2/accessToken",
            json={"appKey": self.app_key, "appSecret": self.app_secret},
        )
        return r.json()

    # ── 知识库 ─────────────────────────────────────────────

    def list_workspaces(self, operator_id=None):
        """
        获取知识库列表。

        API: GET /v2.0/wiki/mineWorkspaces
        权限: Wiki.Workspace.Read

        参数:
            operator_id: unionId

        返回: {"workspace": {"name":"...", "workspaceId":"...", "rootNodeId":"...", ...}}
        """
        r = self._client.get(
            f"{self.BASE}/v2.0/wiki/mineWorkspaces",
            params={"operatorId": self._op(operator_id)},
            headers=self._headers(),
        )
        return self._check(r).json()

    def list_nodes(self, workspace_id, parent_node_id, operator_id=None):
        """
        列出知识库下指定节点的子文档/文件夹。

        API: GET /v2.0/wiki/nodes
        权限: Wiki.Node.Read

        参数:
            workspace_id:   知识库 ID（来自 list_workspaces 的 workspaceId）
            parent_node_id: 父节点 ID（来自 list_workspaces 的 rootNodeId，或文件夹 nodeId）
            operator_id:    unionId

        返回: {"nodes": [{"name":"...", "nodeId":"...", "url":"...", "extension":"adoc", ...}]}
        """
        r = self._client.get(
            f"{self.BASE}/v2.0/wiki/nodes",
            params={
                "operatorId": self._op(operator_id),
                "workspaceId": workspace_id,
                "parentNodeId": parent_node_id,
            },
            headers=self._headers(),
        )
        return self._check(r).json()

    def get_node(self, node_id, operator_id=None):
        """
        获取节点元信息。

        API: GET /v2.0/wiki/nodes/{nodeId}
        权限: Wiki.Node.Read

        参数:
            node_id:     节点 ID（可传 URL，内部自动提取）
            operator_id: unionId

        返回: {"node": {"name":"...", "nodeId":"...", "url":"...", "extension":"...", "workspaceId":"...", ...}}
        """
        node_id = self.extract_node_id(node_id)
        r = self._client.get(
            f"{self.BASE}/v2.0/wiki/nodes/{node_id}",
            params={"operatorId": self._op(operator_id)},
            headers=self._headers(),
        )
        return self._check(r).json()

    # ── 文档：创建 ──────────────────────────────────────────

    def create_doc(self, workspace_id, name, doc_type, operator_id=None,
                   parent_node_id=None):
        """
        在知识库中创建文档。

        API: POST /v1.0/doc/workspaces/{workspaceId}/docs
        权限: Document.WorkspaceDocument.Write

        参数:
            workspace_id:   知识库 ID
            name:           文档名称
            doc_type:       "DOC" | "WORKBOOK" | "MIND"
            operator_id:    unionId
            parent_node_id: 父节点 ID（可选，None=根目录）

        返回: {"dentryUuid":"...", "docKey":"...", "nodeId":"...", "url":"...", "workspaceId":"..."}
        """
        body = {
            "name": name,
            "docType": doc_type,
            "operatorId": self._op(operator_id),
        }
        if parent_node_id:
            body["parentNodeId"] = parent_node_id
        r = self._client.post(
            f"{self.BASE}/v1.0/doc/workspaces/{workspace_id}/docs",
            headers=self._headers(),
            json=body,
        )
        return self._check(r).json()

    # ── 文档：块元素 ────────────────────────────────────────

    def get_doc_blocks(self, doc_key, operator_id=None, start_index=None,
                       end_index=None, block_type=None):
        """
        查询文档根节点下的一级块元素。

        API: GET /v1.0/doc/suites/documents/{docKey}/blocks
        权限: Storage.File.Read

        参数:
            doc_key:      文档 docKey 或 dentryUuid
            operator_id:  unionId
            start_index:  起始位置（可选）
            end_index:    结束位置（可选）
            block_type:   块类型过滤（可选）

        返回: {"data": [{"blockId":"...", "blockType":"paragraph", "paragraph":{"text":"..."}}, ...]}
        """
        params = {"operatorId": self._op(operator_id)}
        if start_index is not None:
            params["startIndex"] = start_index
        if end_index is not None:
            params["endIndex"] = end_index
        if block_type:
            params["blockType"] = block_type
        r = self._client.get(
            f"{self.BASE}/v1.0/doc/suites/documents/{doc_key}/blocks",
            params=params,
            headers=self._headers(),
        )
        return self._check(r).json()

    def insert_block(self, doc_key, element, operator_id=None, index=None):
        """
        插入块元素。

        API: POST /v1.0/doc/suites/documents/{docKey}/blocks
        权限: Storage.File.Write

        参数:
            doc_key:     文档 docKey 或 dentryUuid
            element:     块元素对象
            operator_id: unionId
            index:       插入位置（可选，None=末尾）

        返回: API 响应（含 blockId）
        """
        body = {"operatorId": self._op(operator_id), "element": element}
        if index is not None:
            body["index"] = index
        r = self._client.post(
            f"{self.BASE}/v1.0/doc/suites/documents/{doc_key}/blocks",
            headers=self._headers(),
            json=body,
        )
        return self._check(r).json()

    def update_block(self, doc_key, block_id, element, operator_id=None):
        """
        更新块元素。

        API: PUT /v1.0/doc/suites/documents/{docKey}/blocks/{blockId}
        权限: Storage.File.Write

        参数:
            doc_key:     文档 docKey 或 dentryUuid
            block_id:    块元素 ID（来自 get_doc_blocks 返回的 blockId）
            element:     新的块元素对象
            operator_id: unionId

        返回: API 响应
        """
        r = self._client.put(
            f"{self.BASE}/v1.0/doc/suites/documents/{doc_key}/blocks/{block_id}",
            headers=self._headers(),
            json={"operatorId": self._op(operator_id), "element": element},
        )
        return self._check(r).json()

    def delete_block(self, doc_key, block_id, operator_id=None):
        """
        删除块元素。

        API: DELETE /v1.0/doc/suites/documents/{docKey}/blocks/{blockId}
        权限: Storage.File.Write

        参数:
            doc_key:     文档 docKey 或 dentryUuid
            block_id:    块元素 ID
            operator_id: unionId

        返回: API 响应
        """
        r = self._client.delete(
            f"{self.BASE}/v1.0/doc/suites/documents/{doc_key}/blocks/{block_id}",
            params={"operatorId": self._op(operator_id)},
            headers=self._headers(),
        )
        return self._check(r).json()

    # ── 文档：内容覆写/插入 ────────────────────────────────

    def overwrite_content(self, doc_key, content, operator_id=None):
        """
        以 Markdown 覆写整篇文档。

        API: POST /v1.0/doc/suites/documents/{docKey}/overwriteContent
        权限: Storage.File.Write

        参数:
            doc_key:     文档 docKey 或 dentryUuid
            content:     Markdown 字符串
            operator_id: unionId

        返回: {"success": true, "result": {}}
        """
        r = self._client.post(
            f"{self.BASE}/v1.0/doc/suites/documents/{doc_key}/overwriteContent",
            headers=self._headers(),
            json={"operatorId": self._op(operator_id), "content": content},
        )
        return self._check(r).json()

    # ── 表格 ───────────────────────────────────────────────

    def list_sheets(self, doc_key, operator_id=None):
        """
        列出表格工作表。

        API: GET /v1.0/doc/workbooks/{docKey}/sheets
        权限: Document.Workbook.Read

        参数:
            doc_key:     表格 docKey 或 dentryUuid
            operator_id: unionId

        返回: {"value": [{"name":"Sheet1", "id":"xxx"}, ...]}
        """
        r = self._client.get(
            f"{self.BASE}/v1.0/doc/workbooks/{doc_key}/sheets",
            params={"operatorId": self._op(operator_id)},
            headers=self._headers(),
        )
        return self._check(r).json()

    def read_range(self, doc_key, sheet_id, cell_range, operator_id=None):
        """
        读取表格区域数据。

        API: GET /v1.0/doc/workbooks/{docKey}/sheets/{sheetId}/ranges/{range}
        权限: Document.Workbook.Read

        参数:
            doc_key:     表格 docKey 或 dentryUuid
            sheet_id:    工作表 ID（来自 list_sheets）
            cell_range:  区域，如 "A1:D100"
            operator_id: unionId

        返回: {"displayValues": [["a","b"], ["c","d"]]}
        """
        r = self._client.get(
            f"{self.BASE}/v1.0/doc/workbooks/{doc_key}/sheets/{sheet_id}/ranges/{cell_range}",
            params={"operatorId": self._op(operator_id)},
            headers=self._headers(),
        )
        return self._check(r).json()

    def write_range(self, doc_key, sheet_id, cell_range, values, operator_id=None):
        """
        写入表格区域数据。

        API: PUT /v1.0/doc/workbooks/{docKey}/sheets/{sheetId}/ranges/{range}
        权限: Document.Workbook.Write

        参数:
            doc_key:     表格 docKey 或 dentryUuid
            sheet_id:    工作表 ID
            cell_range:  目标区域，如 "A1:C3"
            values:      二维数组
            operator_id: unionId

        返回: API 响应
        """
        r = self._client.put(
            f"{self.BASE}/v1.0/doc/workbooks/{doc_key}/sheets/{sheet_id}/ranges/{cell_range}",
            headers=self._headers(),
            json={"operatorId": self._op(operator_id), "values": values},
        )
        return self._check(r).json()

    # ── 用户 / 通讯录 ──────────────────────────────────────

    def get_user_by_userid(self, userid):
        """
        通过 userid 查询用户详情。

        API: POST /topapi/v2/user/get
        权限: qyapi_get_member

        参数:
            userid: 员工账号（管理后台 -> 通讯录 -> 员工账号）

        返回: {"errcode":0, "result":{"name":"...", "userid":"...", "unionid":"...", ...}}
        """
        r = self._client.post(
            f"{self.OAPI}/topapi/v2/user/get",
            params={"access_token": self._get_token()},
            json={"userid": userid},
        )
        return r.json()

    def get_user_by_mobile(self, mobile):
        """
        通过手机号查询用户。

        API: POST /topapi/v2/user/getbymobile
        权限: qyapi_get_member_by_mobile

        参数:
            mobile: 手机号

        返回: {"errcode":0, "result":{"userid":"...", "unionid":"...", ...}}
        """
        r = self._client.post(
            f"{self.OAPI}/topapi/v2/user/getbymobile",
            params={"access_token": self._get_token()},
            json={"mobile": mobile},
        )
        return r.json()
