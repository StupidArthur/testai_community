# tool_hub 测试集

工具集 API 自动化测试，仿照 `tests/` 下其他模块按子目录拆分。

## 目录结构

```
tests/tool_hub/
  conftest.py          # autouse bootstrap
  helpers.py           # 创建工具、假制品等辅助函数
  test_auth.py         # 未认证 401
  test_bootstrap.py    # 预置 ai_translate / feature_recorder
  test_list_detail.py  # 列表筛选、详情、下架可见性
  test_create.py       # 创建 platform/client、校验
  test_versions.py     # 新版本、changelog、说明书继承
  test_permissions.py  # 编辑/下架/删除权限
  test_download.py     # 客户端制品下载

tests/fixtures/tool_hub/
  README.md            # fixture 说明
```

## 运行

在 `backend/` 目录：

```powershell
python -m pytest tests/tool_hub -v
```

## 覆盖范围

| 模块 | 用例数 | 说明 |
|------|--------|------|
| 认证 | 5 | 列表/详情/创建/下载/删除无 token |
| Bootstrap | 5 | 内置工具、幂等、说明书 |
| 列表与详情 | 7 | 筛选、下架隐藏、can_edit/can_delete |
| 创建 | 8 | slug 校验、platform 链接、client 制品 |
| 版本 | 5 | changelog、继承 manual、权限 |
| 权限 | 6 | 所有者/非所有者/Admin |
| 下载 | 6 | exe/zip、最新版本、下架 |

共计 **42** 项。
