r"""备份核心逻辑（纯标准库实现，无任何第三方依赖，可在 exe 环境运行）。"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

# ──────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────

DINGTALK_APP_KEY = "dingjvvesrkwup6d8gix"
DINGTALK_APP_SECRET = "fOi7TOrP05h4vm4Ct-a-f_bN7laclYyedEttyz3V6AgCenbQVk7pTuhj-78RQNU4"
WORKBOOK_ID = "14dA3GK8gjgxaZY9CEAPRaNQJ9ekBD76"
OPERATOR_ID = "n3dHYKMrKiSBXj0DlAjqiSFgiEiE"

BACKUP_DIR = Path(r"D:\backups\dingtalk")
KEEP_DAYS = 30

HTTP_CONNECT_TIMEOUT = 10
HTTP_READ_TIMEOUT = 15
HARD_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 2
CHUNK_COLS = "Z"
CHUNK_ROWS = 50
EMPTY_STREAK_LIMIT = 200
API_INTERVAL = 0.5
SHEET_INTERVAL = 1
MAX_CHUNKS = 200

DINGTALK_GETTOKEN_URL = "https://oapi.dingtalk.com/gettoken"
DINGTALK_SHEETS_URL = "https://api.dingtalk.com/v1.0/doc/workbooks/{workbookId}/sheets"
DINGTALK_RANGE_URL = "https://api.dingtalk.com/v1.0/doc/workbooks/{workbookId}/sheets/{sheetId}/ranges/{rangeAddress}"


class DingTalkAPIError(RuntimeError):
    pass


# ──────────────────────────────────────────────────────
#  同步 HTTP（urllib，纯标准库）
# ──────────────────────────────────────────────────────

def _sync_http_get(url: str, headers: dict | None, params: dict | None,
                   connect_timeout: int, read_timeout: int) -> dict:
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    socket.setdefaulttimeout(connect_timeout)
    try:
        resp = urllib.request.urlopen(req, timeout=read_timeout)
        status = resp.status
        raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误 {url}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001 - 兜底，任何网络异常都转成可读错误
        raise RuntimeError(f"请求失败 {url}: {exc}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"响应解析失败 {url} (HTTP {status}): {raw[:200]!r}") from exc

    if status >= 500:
        raise DingTalkAPIError(f"HTTP {status} 服务端错误: {data}")
    if status >= 400:
        raise DingTalkAPIError(f"HTTP {status} 客户端错误: {data}")
    return data


async def _http_get_async(url: str, *, headers: dict | None = None,
                          params: dict | None = None) -> dict:
    return await asyncio.to_thread(
        _sync_http_get, url, headers, params,
        HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT,
    )


async def http_get(url: str, *, headers: dict | None = None,
                   params: dict | None = None, retries: int = MAX_RETRIES) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await asyncio.wait_for(
                _http_get_async(url, headers=headers, params=params),
                timeout=HARD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            last_err = TimeoutError(f"硬超时 {HARD_TIMEOUT}s")
            await asyncio.sleep(RETRY_DELAY)
        except (RuntimeError, DingTalkAPIError) as exc:
            if isinstance(exc, DingTalkAPIError):
                raise
            last_err = exc
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
    raise DingTalkAPIError(f"请求彻底失败（重试 {retries} 次）: {last_err}")


_token_cache: dict = {"token": "", "expire_at": 0.0}


async def get_access_token() -> str:
    now = time.time()
    cached = _token_cache["token"]
    if cached and now < _token_cache["expire_at"]:
        return cached
    data = await http_get(
        DINGTALK_GETTOKEN_URL,
        params={"appkey": DINGTALK_APP_KEY, "appsecret": DINGTALK_APP_SECRET},
    )
    if data.get("errcode", -1) != 0:
        raise DingTalkAPIError(f"gettoken 返回错误: {data}")
    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expire_at"] = now + 5400
    return token


async def get_all_sheets(token: str) -> list[dict]:
    url = DINGTALK_SHEETS_URL.format(workbookId=WORKBOOK_ID)
    headers = {"x-acs-dingtalk-access-token": token}
    params = {"operatorId": OPERATOR_ID}
    data = await http_get(url, headers=headers, params=params)
    return data.get("value", [])


async def get_range_values(token: str, sheet_id: str) -> list[list]:
    headers = {"x-acs-dingtalk-access-token": token}
    params = {"select": "values", "operatorId": OPERATOR_ID}
    all_values: list[list] = []
    row_offset = 1
    empty_streak = 0
    chunk_count = 0

    while chunk_count < MAX_CHUNKS:
        range_addr = f"A{row_offset}:{CHUNK_COLS}{row_offset + CHUNK_ROWS - 1}"
        url = DINGTALK_RANGE_URL.format(
            workbookId=WORKBOOK_ID, sheetId=sheet_id, rangeAddress=range_addr,
        )
        data = await http_get(url, headers=headers, params=params)
        chunk = data.get("values", [])
        if not chunk:
            break

        chunk_empty = sum(1 for row in chunk if all(cell in (None, "", []) for cell in row))
        all_values.extend(chunk)
        chunk_count += 1

        if chunk_empty == len(chunk):
            empty_streak += len(chunk)
        else:
            empty_streak = 0

        if empty_streak >= EMPTY_STREAK_LIMIT:
            break

        if len(chunk) < CHUNK_ROWS:
            break

        row_offset += CHUNK_ROWS
        await asyncio.sleep(API_INTERVAL)

    while all_values and all(cell in (None, "", []) for cell in all_values[-1]):
        all_values.pop()
    return all_values


# ──────────────────────────────────────────────────────
#  手写 xlsx（zipfile + xml，纯标准库）
# ──────────────────────────────────────────────────────

def _col_letter(index: int) -> str:
    """1-based 列号转字母，如 1->A, 27->AA。"""
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_xml(row_idx: int, col_idx: int, value) -> str:
    ref = f"{_col_letter(col_idx)}{row_idx}"
    if value is None or value == "":
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return f'<c r="{ref}"/>'
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(values: list[list]) -> str:
    rows = []
    for row_idx, row in enumerate(values, 1):
        cells = [_cell_xml(row_idx, col_idx, cell_val)
                 for col_idx, cell_val in enumerate(row, 1)]
        rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def _write_xlsx(sheets_data: list[tuple[str, list[list]]], output_path: Path) -> None:
    """用标准库 zipfile 直接生成 xlsx（Open XML 格式）。"""
    sheet_names = [name[:31] if name else f"Sheet{idx}" for idx, (name, _) in enumerate(sheets_data, 1)]

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets_data) + 1)
        )
        + "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, name in enumerate(sheet_names, 1)
        )
        + "</sheets></workbook>"
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets_data) + 1)
        )
        + '<Relationship Id="rIdStyle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf/></cellXfs>'
        "</styleSheet>"
    )

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", styles_xml)
        for i, (_, values) in enumerate(sheets_data, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(values))


def write_to_excel(sheets_data: list[tuple[str, list[list]]], output_path: Path) -> None:
    _write_xlsx(sheets_data, output_path)


def cleanup_old_backups() -> None:
    cutoff = dt.datetime.now() - dt.timedelta(days=KEEP_DAYS)
    for f in BACKUP_DIR.glob("backup_*.xlsx"):
        if f.stat().st_mtime < cutoff.timestamp():
            f.unlink()


class ProgressReporter:
    """备份进度回调接口（与 task_hooks.Callback 解耦，便于本地测试）。"""
    def status(self, msg): pass
    def progress(self, v, msg=None): pass
    def log(self, level, msg): pass
    def error(self, msg): pass


async def async_backup(reporter: ProgressReporter | None = None) -> str:
    """异步备份主流程，通过 reporter 报告进度。"""
    if reporter is None:
        reporter = ProgressReporter()

    t_total = time.time()
    reporter.status("开始备份")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    token = await get_access_token()
    reporter.log("info", "access_token 获取成功")

    sheets = await get_all_sheets(token)
    reporter.log("info", f"共 {len(sheets)} 个工作表: {[s['name'] for s in sheets]}")

    if not sheets:
        return "未获取到任何工作表"

    sheets_data: list[tuple[str, list[list]]] = []
    for idx, sheet in enumerate(sheets, 1):
        sheet_id = sheet["id"]
        sheet_name = sheet["name"]
        reporter.status(f"读取中 [{idx}/{len(sheets)}] {sheet_name}")

        t0 = time.time()
        try:
            values = await get_range_values(token, sheet_id)
            elapsed = time.time() - t0
            reporter.log("info", f"[{idx}/{len(sheets)}] {sheet_name}: {len(values)} 行 ({elapsed:.1f}s)")
            sheets_data.append((sheet_name, values))
        except DingTalkAPIError as exc:
            reporter.log("error", f"[{idx}/{len(sheets)}] {sheet_name} 读取失败: {exc}")
            sheets_data.append((sheet_name, []))

        if idx < len(sheets):
            await asyncio.sleep(SHEET_INTERVAL)

        reporter.progress(int(idx / len(sheets) * 90), f"工作表 {idx}/{len(sheets)}")

    if not any(values for _, values in sheets_data):
        return "所有工作表都读取失败"

    reporter.status("正在写入 Excel")
    now = dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    output_path = BACKUP_DIR / f"backup_{stamp}.xlsx"
    write_to_excel(sheets_data, output_path)

    file_size = output_path.stat().st_size
    total_rows = sum(len(v) for _, v in sheets_data)
    total_elapsed = time.time() - t_total

    cleanup_old_backups()
    reporter.progress(100, "完成")

    result = f"备份完成: {output_path} ({file_size / 1024:.1f} KB, {total_rows} 行, {total_elapsed:.1f}s)"
    reporter.status("备份完成")
    reporter.log("info", result)
    return result
