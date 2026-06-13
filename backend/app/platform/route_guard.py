"""启动时路由鉴权静态检查（非登录鉴权，见模块文档）。"""

from __future__ import annotations

from fastapi import APIRouter

# 允许无 JWT 的公开路由 (method, path)
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/health"),
}

# 视为已挂载鉴权的 Depends 名称（由各业务 App 的 auth 模块提供）
AUTH_DEPENDENCY_NAMES = frozenset({
    "get_current_user_by_ticket",
    "get_current_user",
    "RequireRole",
    "verify_api_key",
})


def _collect_dep_names(dependant) -> set[str]:
    names: set[str] = set()
    for d in dependant.dependencies:
        name = getattr(d.call, "__name__", None) or type(d.call).__name__
        names.add(name)
        names.update(_collect_dep_names(d))
    return names


def _full_route_path(prefix: str, path: str) -> str:
    """拼接 router prefix 与 route.path，避免重复前缀。"""
    prefix = (prefix or "").rstrip("/")
    if not prefix:
        return path
    if path == prefix or path.startswith(prefix + "/"):
        return path
    if path.startswith("/"):
        return f"{prefix}{path}"
    return f"{prefix}/{path}"


def assert_router_protected(router: APIRouter, *, label: str = "") -> None:
    """启动时断言：除 PUBLIC_ROUTES 外，路由须挂载已知鉴权 Depends。"""
    prefix = getattr(router, "prefix", "") or ""

    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        full_path = _full_route_path(prefix, path)

        for method in methods:
            if method.upper() == "HEAD":
                continue
            if (method.upper(), full_path) in PUBLIC_ROUTES:
                continue

            all_deps = _collect_dep_names(route.dependant)
            if not all_deps.intersection(AUTH_DEPENDENCY_NAMES):
                tag = f"{label} " if label else ""
                raise RuntimeError(
                    f"[安全] {tag}路由 {method} {full_path} 缺少鉴权依赖，"
                    f"实际依赖: {all_deps}"
                )
