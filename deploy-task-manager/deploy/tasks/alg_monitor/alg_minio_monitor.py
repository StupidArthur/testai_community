"""
alg_minio_monitor.py -- alg 桶监控模块。

提供两个客户端，分别对应两种后端：

  AlgMinioMonitor   MinIO Console API 客户端（/api/v1/login + /api/v1/buckets/.../objects）
                    适用于 MinIO（Console 与 S3 不同端口时，base_url 指向 Console 端口）
  AlgRustfsMonitor  S3 协议客户端（boto3.list_objects_v2）
                    适用于 RustFS（只提供 S3，无 Console API），也可用于 MinIO 的 S3 端口

两个客户端共享 AlgObject 数据结构与时间字段语义。

用法:
    # MinIO（Console API）
    mon = AlgMinioMonitor("http://10.10.58.153:31283", "admin", "Supcon1304")
    mon.login()

    # RustFS（S3 API，端口 31014）
    mon = AlgRustfsMonitor("http://devgoto.supcon5t.com:31014", "admin", "Supcon@1304")
    mon.connect()
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import boto3
import httpx
from botocore.client import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

# 默认时区：东八区
TZ_CST = timezone(timedelta(hours=8))

# list_objects_v2 单页最大 1000（受 S3 协议限制），超过自动翻页
S3_PAGE_SIZE = 1000

# MinIO Console API 端点
LOGIN_PATH = "/api/v1/login"
OBJECTS_PATH = "/api/v1/buckets/{bucket}/objects"

# 目录占位符的零值时间（MinIO Console 用法）
ZERO_TIME = "0001-01-01T00:00:00Z"

# 递归下钻的最大目录深度（MinIO Console）
MAX_DEPTH = 5


@dataclass
class AlgObject:
    """alg 桶下的一个对象（文件或目录）。"""
    name: str                # 完整对象名（含路径前缀）
    size: int = 0            # 字节数（目录为 0）
    last_modified: str = ""  # 上传时间（东八区字符串）
    is_dir: bool = False     # 是否目录


def _to_local_str(dt, tz: timezone) -> str:
    """datetime -> 东八区 'YYYY-MM-DD HH:MM:SS'。None/异常时返回空串。"""
    if dt is None:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _to_local_from_iso(utc_str: str, tz: timezone) -> str:
    """UTC ISO8601 串 -> 东八区 'YYYY-MM-DD HH:MM:SS'。零值/无法解析时原样返回。"""
    if not utc_str or utc_str == ZERO_TIME:
        return utc_str
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return utc_str


def _parse_local(s: str, tz: timezone) -> datetime | None:
    """把 _to_local_* 产出的本地时间字符串解析回 datetime。空串/零值/异常返回 None。"""
    if not s or s == ZERO_TIME:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    except Exception:
        return None


def _filter_last_24h(objs: list[AlgObject], tz: timezone) -> list[AlgObject]:
    """过滤掉目录，返回最近 24 小时内有更新的文件。"""
    cutoff = datetime.now(tz) - timedelta(hours=24)
    result: list[AlgObject] = []
    for obj in objs:
        if obj.is_dir:
            continue
        dt = _parse_local(obj.last_modified, tz)
        if dt is not None and dt >= cutoff:
            result.append(obj)
    return result


# ============================================================
# MinIO Console API 客户端
# ============================================================

class AlgMinioMonitor:
    """MinIO Console API 客户端（聚焦 resource/ 目录）。"""

    def __init__(
        self,
        base_url: str,
        access_key: str,
        secret_key: str,
        timeout: float = 15.0,
        tz: timezone = TZ_CST,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.tz = tz
        self.client = httpx.Client(
            base_url=self.base_url, timeout=timeout, follow_redirects=True
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------- API 1: 登录 ----------------

    def login(self) -> bool:
        """登录 MinIO Console，成功返回 True。

        成功时服务端返回 204 并种下 session cookie，由 httpx.Client 自动保存，
        后续列对象请求复用该 cookie 通过鉴权。
        """
        resp = self.client.post(
            LOGIN_PATH,
            json={"accessKey": self.access_key, "secretKey": self.secret_key},
        )
        ok = resp.status_code == 204
        if not ok:
            log.error("login failed: %s %s", resp.status_code, resp.text[:200])
        return ok

    # ---------------- API 2: 列对象 ----------------

    def list_objects(
        self,
        bucket: str = "alg",
        prefix: str = "",
        recursive: bool = True,
        limit: int = 500,
    ) -> list[AlgObject]:
        """列 bucket 下指定前缀的对象。

        参数:
          bucket:    bucket 名称，默认 alg
          prefix:    路径前缀（如 "resource/"），空串表示根目录
          recursive: True=递归下钻所有子目录；False=只列当前层
          limit:     单次请求最大返回数（Console API 默认仅 20，需手动调大）
        """
        if recursive:
            return self._list_recursive(bucket, prefix, limit)
        return self._list_once(bucket, prefix, limit)

    def list_resource(self, recursive: bool = True, limit: int = 500) -> list[AlgObject]:
        """列 alg/resource/ 下的对象（监控主入口）。"""
        return self.list_objects(
            bucket="alg", prefix="resource/", recursive=recursive, limit=limit
        )

    def get_alg_info_in_one_day(self) -> list[AlgObject]:
        """返回 resource/ 下最近 24 小时内有更新的算法文件（仅直接子文件，不递归子目录）。"""
        return _filter_last_24h(self.list_resource(recursive=False), self.tz)

    # ---------------- 内部实现 ----------------

    def _list_once(self, bucket: str, prefix: str, limit: int) -> list[AlgObject]:
        """单层列举：调一次 API 2。"""
        encoded = base64.b64encode(prefix.encode()).decode()
        resp = self.client.get(
            OBJECTS_PATH.format(bucket=bucket),
            params={"prefix": encoded, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        objects = data.get("objects") or []
        result: list[AlgObject] = []
        for o in objects:
            name = o.get("name", "")
            result.append(AlgObject(
                name=prefix + name if not name.startswith(prefix) else name,
                size=o.get("size") or 0,
                last_modified=_to_local_from_iso(o.get("last_modified", ""), self.tz),
                is_dir=name.endswith("/"),
            ))
        return result

    def _list_recursive(
        self, bucket: str, prefix: str, limit: int, depth: int = 0
    ) -> list[AlgObject]:
        """递归列举：每发现一个子目录就多调一次 API 2 下钻。"""
        items = self._list_once(bucket, prefix, limit)
        result: list[AlgObject] = []
        for item in items:
            if item.is_dir and depth < MAX_DEPTH:
                result.extend(self._list_recursive(bucket, item.name, limit, depth + 1))
            else:
                result.append(item)
        return result


# ============================================================
# RustFS / MinIO S3 客户端（boto3）
# ============================================================

class AlgRustfsMonitor:
    """S3 协议客户端（boto3），适用于 RustFS，也可指向 MinIO 的 S3 端口。"""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        timeout: float = 15.0,
        tz: timezone = TZ_CST,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.tz = tz
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=timeout,
                read_timeout=timeout,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------- 鉴权探活 ----------------

    def connect(self) -> bool:
        """探活：调一次 head_bucket 验证鉴权可用，成功返回 True。"""
        try:
            self.client.head_bucket(Bucket="alg")
            return True
        except ClientError as e:
            log.error("connect failed: %s", e)
            return False

    # ---------------- 列对象 ----------------

    def list_objects(
        self,
        bucket: str = "alg",
        prefix: str = "",
        recursive: bool = True,
        limit: int = S3_PAGE_SIZE,
    ) -> list[AlgObject]:
        """列 bucket 下指定前缀的对象。

        参数:
          bucket:    bucket 名称，默认 alg
          prefix:    路径前缀（如 "resource/"），空串表示根目录
          recursive: True=扁平列出所有子文件；False=只列当前层（含子目录）
          limit:     单次请求最大返回数（S3 上限 1000）
        """
        if recursive:
            return self._list_flat(bucket, prefix, limit)
        return self._list_layered(bucket, prefix, limit)

    def list_resource(self, recursive: bool = True, limit: int = S3_PAGE_SIZE) -> list[AlgObject]:
        """列 alg/resource/ 下的对象（监控主入口）。"""
        return self.list_objects(
            bucket="alg", prefix="resource/", recursive=recursive, limit=limit
        )

    def get_alg_info_in_one_day(self) -> list[AlgObject]:
        """返回 resource/ 下最近 24 小时内有更新的算法文件（仅直接子文件，不递归子目录）。"""
        return _filter_last_24h(self.list_resource(recursive=False), self.tz)

    # ---------------- 内部实现 ----------------

    def _list_flat(self, bucket: str, prefix: str, limit: int) -> list[AlgObject]:
        """扁平列举：不带 Delimiter，一次性拿到前缀下所有 key（按 MaxKeys 翻页）。"""
        result: list[AlgObject] = []
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": limit}
        while True:
            resp = self.client.list_objects_v2(**kwargs)
            for o in resp.get("Contents") or []:
                key = o.get("Key", "")
                if key.endswith("/"):
                    continue
                result.append(AlgObject(
                    name=key,
                    size=o.get("Size") or 0,
                    last_modified=_to_local_str(o.get("LastModified"), self.tz),
                    is_dir=False,
                ))
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp.get("NextContinuationToken")
        return result

    def _list_layered(self, bucket: str, prefix: str, limit: int) -> list[AlgObject]:
        """分层列举：Delimiter='/'，返回当前层文件 + 子目录前缀。"""
        result: list[AlgObject] = []
        kwargs = {
            "Bucket": bucket,
            "Prefix": prefix,
            "Delimiter": "/",
            "MaxKeys": limit,
        }
        while True:
            resp = self.client.list_objects_v2(**kwargs)
            for o in resp.get("Contents") or []:
                key = o.get("Key", "")
                if key.endswith("/"):
                    continue
                result.append(AlgObject(
                    name=key,
                    size=o.get("Size") or 0,
                    last_modified=_to_local_str(o.get("LastModified"), self.tz),
                    is_dir=False,
                ))
            for p in resp.get("CommonPrefixes") or []:
                result.append(AlgObject(
                    name=p.get("Prefix", ""),
                    size=0,
                    last_modified="",
                    is_dir=True,
                ))
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp.get("NextContinuationToken")
        return result


# ============================================================
# demo
# ============================================================

if __name__ == "__main__":
    import sys

    backend = sys.argv[1] if len(sys.argv) > 1 else "minio"

    if backend == "minio":
        with AlgMinioMonitor("http://10.10.58.153:31283", "admin", "Supcon1304") as mon:
            if not mon.login():
                raise SystemExit("login failed")
            files = mon.list_resource(recursive=True)
    elif backend == "rustfs":
        with AlgRustfsMonitor("http://devgoto.supcon5t.com:31014", "admin", "Supcon@1304") as mon:
            if not mon.connect():
                raise SystemExit("connect failed")
            files = mon.list_resource(recursive=True)
    else:
        raise SystemExit(f"unknown backend: {backend}")

    print(f"[{backend}] total: {len(files)}")
    for f in files[:20]:
        print(f"{f.last_modified}  {f.size:>12,}  {f.name}")
