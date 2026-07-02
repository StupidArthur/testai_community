"""知识库端到端探测脚本（本地 API）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:48010"
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kb_sample.md"


def main() -> int:
    issues: list[str] = []
    token = httpx.post(
        f"{BASE}/api/auth/login",
        json={"username": "admin", "password": "admin"},
        timeout=30,
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = httpx.get(f"{BASE}/api/knowledge-base/bases/default", headers=h, timeout=30)
    print("default_kb", r.status_code)
    if r.status_code != 200:
        print(r.text)
        return 1
    kb_id = r.json()["id"]
    print("kb_id", kb_id)

    r2 = httpx.post(
        f"{BASE}/api/knowledge-base/bases",
        json={"name": "x", "description": ""},
        headers=h,
        timeout=30,
    )
    print("create_second_kb", r2.status_code, r2.json().get("detail"))

    content = FIX.read_bytes()
    files = {"file": ("kb_sample.md", content, "text/markdown")}
    r3 = httpx.post(
        f"{BASE}/api/knowledge-base/bases/{kb_id}/documents",
        headers=h,
        files=files,
        timeout=120,
    )
    print("direct_upload", r3.status_code, r3.text[:300])
    doc_id = r3.json().get("id") if r3.status_code == 201 else None

    if doc_id:
        doc = None
        for i in range(30):
            detail = httpx.get(f"{BASE}/api/knowledge-base/bases/{kb_id}", headers=h, timeout=30).json()
            doc = next((x for x in detail["documents"] if x["id"] == doc_id), None)
            status = doc["status"] if doc else None
            err = doc.get("error") if doc else None
            print(f"  doc poll {i}: status={status} error={err}")
            if doc and status in ("ready", "failed"):
                if status == "failed":
                    issues.append(f"direct upload failed: {err}")
                break
            time.sleep(2)
        else:
            issues.append("direct upload timeout (still queued/processing)")

    data = {
        "doc_type": "general",
        "product": "TestApp",
        "version": "v1",
        "environment": "",
        "note": "auto test",
    }
    r4 = httpx.post(
        f"{BASE}/api/data-cleaning/jobs",
        headers=h,
        data=data,
        files=files,
        timeout=120,
    )
    print("clean_upload", r4.status_code, r4.text[:400])
    job_id = r4.json().get("id") if r4.status_code == 201 else None
    if r4.status_code != 201:
        issues.append(f"clean upload failed: {r4.text[:200]}")

    job = {}
    if job_id:
        for i in range(60):
            job = httpx.get(f"{BASE}/api/data-cleaning/jobs/{job_id}", headers=h, timeout=60).json()
            print(
                f"  job poll {i}: status={job['status']} "
                f"paragraphs={len(job.get('paragraphs') or [])} error={job.get('error')}"
            )
            if job["status"] in ("pending_review", "failed", "approved"):
                break
            time.sleep(3)
        else:
            issues.append("clean job timeout")

        if job.get("status") == "failed":
            issues.append(f"clean job failed: {job.get('error')}")
        elif job.get("status") == "pending_review":
            if not job.get("paragraphs"):
                issues.append("pending_review but zero paragraphs (split/LLM issue)")
            else:
                r5 = httpx.post(
                    f"{BASE}/api/data-cleaning/jobs/{job_id}/approve",
                    headers=h,
                    json={},
                    timeout=300,
                )
                print("approve", r5.status_code, r5.text[:300])
                if r5.status_code != 200:
                    issues.append(f"approve failed: {r5.text[:200]}")

    r6 = httpx.post(
        f"{BASE}/api/knowledge-base/bases/{kb_id}/chat",
        headers=h,
        json={"question": "验证码有效期多久？"},
        timeout=180,
    )
    print("chat", r6.status_code, r6.text[:400])
    if r6.status_code != 200:
        issues.append(f"chat failed: {r6.text[:200]}")

    print("\n=== ISSUES ===")
    for item in issues:
        print("-", item)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
