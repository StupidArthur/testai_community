# RAG Pipeline 文档清洗与切片

## 目标

产品手册（`.docx` / `.pdf` / `.md`）经 **零 LLM 入库** Pipeline 切分为 chunk，写入 Chroma，供问答使用。

## 铁律

1. 入库全流程不使用 LLM **生成**任何内容（允许 Embedding 向量化）。
2. 原文是唯一真相源：`raw_text` 与清洗后原文逐字一致，只删噪音。
3. AI 仅在 `POST /qa/ask` 时组织回答，并做实体校验。

## 目录

```
rag_pipeline/
├── main.py                 # FastAPI：upload / status / ask
├── config.py               # 阈值与路径常量
├── pipeline/
│   ├── converter.py        # 阶段零
│   ├── cleaner.py          # 阶段一
│   ├── parser.py           # 阶段二
│   ├── chunker.py          # 阶段三
│   ├── annotator.py        # 阶段四
│   ├── qa.py               # 阶段五质检去重
│   └── pipeline.py         # 串联
├── qa/                     # 提问时检索与生成
├── vectorstore/            # Chroma + embedding
├── models/schemas.py
└── tests/
```

## 阶段说明

| 阶段 | 模块 | 要点 |
|------|------|------|
| 零 | converter | md 直读；docx→pandoc；pdf→pdfplumber |
| 一 | cleaner | 删图/尺寸标记/裸链；下划线去标记留正文；压空行 |
| 二 | parser | MD 标题 + 编号伪标题；表格/列表块；章节路径 |
| 三 | chunker | 标题绑首段；软上限 500；`chunk_text=[路径]\\n原文` |
| 四 | annotator | 规则摘要/实体/邻接 |
| 五 | qa | 杜撰检测、覆盖率≥95%、精确/SimHash/余弦去重 |

向量库：**Chroma**。Embedding：Ollama（`OLLAMA_EMBED_MODEL`，默认 `bge-m3:latest`），不可用时降级 hash（仅开发/测试）。

## API

- `POST /documents/upload`：上传并跑完整 pipeline
- `GET /documents/{doc_id}/status`：状态与质检报告
- `POST /qa/ask`：检索 + LLM 回答 + 实体校验失败则回退原文

## 本地验证

```powershell
cd D:\代码\testai_community
$env:PYTHONPATH = "D:\代码\testai_community"
pip install -r rag_pipeline\requirements.txt
python -m pytest rag_pipeline\tests\test_pipeline.py -q
python -m rag_pipeline.pipeline.pipeline
```

启动 API：

```powershell
$env:PYTHONPATH = "D:\代码\testai_community"
python -m rag_pipeline.main
```

docx 需安装 pandoc，或设置 `PANDOC_PATH`。

## 与现有 knowledge_base 关系

- 独立包 `rag_pipeline/` 仍可单独跑 API（默认端口 48021）。
- **网页知识库清洗入库（3003 / 后端 data_cleaning）** 已简易接入同一铁律：
  - `CLEAN_USE_LLM_ESSENCE=False`（默认）
  - 规则 `clean_noise` 删噪 → 切段 → `essence_markdown = raw_text`
  - 前端文案为「正文（可编辑）」，不再做 LLM 库内对比
- 完整五阶段质检 / 章节路径切块尚未灌入 ParagraphUnit；需要时可再加深接入。
