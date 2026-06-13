"""python -m app.ai_service.news 入口。"""

from __future__ import annotations

import asyncio
import logging

from app.ai_service.news.pipeline import _run_default


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(_run_default())
    if result.output_path:
        print(f"[OK] 成功生成本地报告：{result.output_path.resolve()}")
        if result.invalid_links:
            print(f"[WARN] 含 {len(result.invalid_links)} 条非白名单链接，请人工核对")
    elif not result.search.llm_context.strip():
        print("今天没有搜索到有价值的新闻。")
    else:
        print("生成完成（未写入文件）。")


if __name__ == "__main__":
    main()
