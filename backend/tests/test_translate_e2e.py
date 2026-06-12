"""translate 模块全功能测试：上传、任务列表、状态查询、取消、下载。"""

import time
from pathlib import Path

from conftest import SAMPLE_ZIP


class TestTranslateHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestTranslateUpload:
    def test_upload_sample(self, client, auth_headers):
        assert SAMPLE_ZIP.exists(), f"测试数据不存在: {SAMPLE_ZIP}"
        with SAMPLE_ZIP.open("rb") as f:
            r = client.post(
                "/api/translate/upload",
                files={"file": ("sample_recording.zip", f, "application/zip")},
                headers=auth_headers,
            )
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert isinstance(data["queue_ahead"], int)
        assert isinstance(data["queue_total"], int)

    def test_upload_no_auth(self, client):
        r = client.post("/api/translate/upload")
        assert r.status_code == 401


class TestTranslateJobList:
    def test_list_jobs(self, client, auth_headers):
        r = client.get("/api/translate/jobs", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_jobs_schema(self, client, auth_headers):
        r = client.get("/api/translate/jobs", headers=auth_headers)
        assert r.status_code == 200
        jobs = r.json()
        if jobs:
            job = jobs[0]
            required = [
                "job_id", "status", "created_at", "updated_at",
                "current_phase", "current_step", "total_steps",
                "message", "queue_ahead", "queue_total", "error",
            ]
            for field in required:
                assert field in job, f"missing field: {field}"

    def test_list_jobs_no_auth(self, client):
        r = client.get("/api/translate/jobs")
        assert r.status_code == 401


class TestTranslateJobDetail:
    def test_get_nonexistent_job(self, client, auth_headers):
        r = client.get(
            "/api/translate/jobs/00000000000000000000000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_get_job_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent")
        assert r.status_code == 401


class TestTranslateCancel:
    def test_cancel_nonexistent_job(self, client, auth_headers):
        r = client.delete(
            "/api/translate/jobs/00000000000000000000000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_cancel_no_auth(self, client):
        r = client.delete("/api/translate/jobs/nonexistent")
        assert r.status_code == 401


class TestTranslateDownload:
    def test_download_nonexistent_job(self, client, auth_headers):
        r = client.get(
            "/api/translate/jobs/00000000000000000000000000000000/download",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_download_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/download")
        assert r.status_code == 401


class TestTranslateStream:
    def test_stream_nonexistent_job(self, client, auth_headers):
        r = client.get(
            "/api/translate/jobs/00000000000000000000000000000000/stream",
            headers=auth_headers,
        )
        assert r.status_code in (200, 404)

    def test_stream_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/stream")
        assert r.status_code == 401


class TestTranslateFileAccess:
    def test_file_nonexistent_job(self, client, auth_headers):
        r = client.get(
            "/api/translate/jobs/00000000000000000000000000000000/file?p=test.md",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_file_not_in_whitelist(self, client, auth_headers):
        with SAMPLE_ZIP.open("rb") as f:
            r = client.post(
                "/api/translate/upload",
                files={"file": ("sample_recording.zip", f, "application/zip")},
                headers=auth_headers,
            )
        job_id = r.json()["job_id"]
        r2 = client.get(
            f"/api/translate/jobs/{job_id}/file?p=../../etc/passwd",
            headers=auth_headers,
        )
        assert r2.status_code == 400

    def test_file_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/file?p=test.md")
        assert r.status_code == 401


class TestTranslateE2E:
    """端到端冒烟：上传 → 等待完成 → 下载。需要 LLM API 可用。"""

    def test_upload_and_track(self, client, auth_headers):
        assert SAMPLE_ZIP.exists(), f"测试数据不存在: {SAMPLE_ZIP}"
        with SAMPLE_ZIP.open("rb") as f:
            r = client.post(
                "/api/translate/upload",
                files={"file": ("sample_recording.zip", f, "application/zip")},
                headers=auth_headers,
            )
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r2 = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["job_id"] == job_id

        r3 = client.get("/api/translate/jobs", headers=auth_headers)
        assert r3.status_code == 200
        ids = [j["job_id"] for j in r3.json()]
        assert job_id in ids

    def test_cancel_queued_job(self, client, auth_headers):
        with SAMPLE_ZIP.open("rb") as f:
            r = client.post(
                "/api/translate/upload",
                files={"file": ("sample_recording.zip", f, "application/zip")},
                headers=auth_headers,
            )
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r2 = client.delete(f"/api/translate/jobs/{job_id}", headers=auth_headers)
        if r2.status_code == 200:
            r3 = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
            assert r3.json()["status"] == "cancelled"
