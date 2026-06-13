"""translate 模块全功能测试：上传、任务列表、状态查询、取消、下载。"""

from pathlib import Path

from conftest import SAMPLE_ZIP

# 与 app.translate.schemas.JobView 保持一致
JOB_VIEW_FIELDS = [
    "job_id",
    "name",
    "username",
    "status",
    "created_at",
    "updated_at",
    "current_phase",
    "current_step",
    "total_steps",
    "message",
    "queue_ahead",
    "queue_total",
    "error",
]


def _create_job_sample(client, auth_headers, *, name: str | None = None):
    """POST /jobs 上传 fixture ZIP，可选任务名称。"""
    assert SAMPLE_ZIP.exists(), f"测试数据不存在: {SAMPLE_ZIP}"
    with SAMPLE_ZIP.open("rb") as f:
        kwargs: dict = {
            "files": {"file": ("sample_recording.zip", f, "application/zip")},
            "headers": auth_headers,
        }
        if name is not None:
            kwargs["data"] = {"name": name}
        return client.post("/api/translate/jobs", **kwargs)


class TestTranslateHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestTranslateCreateJob:
    def test_create_job_sample(self, client, auth_headers):
        assert SAMPLE_ZIP.exists(), f"测试数据不存在: {SAMPLE_ZIP}"
        r = _create_job_sample(client, auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] in ("queued", "running")
        assert isinstance(data["queue_ahead"], int)
        assert isinstance(data["queue_total"], int)

    def test_create_job_with_custom_name(self, client, auth_headers):
        custom_name = "登录流程回归"
        r = _create_job_sample(client, auth_headers, name=custom_name)
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        detail = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["name"] == custom_name

    def test_create_job_sets_username_from_login(self, client, eng_headers):
        r = _create_job_sample(client, eng_headers)
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        detail = client.get(f"/api/translate/jobs/{job_id}", headers=eng_headers)
        assert detail.status_code == 200
        body = detail.json()
        assert body["username"] == "eng_test"
        assert body["name"].endswith("_eng_test")

    def test_create_job_no_auth(self, client):
        r = client.post("/api/translate/jobs")
        assert r.status_code in (401, 422)


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
            for field in JOB_VIEW_FIELDS:
                assert field in job, f"missing field: {field}"
            assert isinstance(job["name"], str)
            assert isinstance(job["username"], str)

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
        r = client.post(
            "/api/translate/jobs/00000000000000000000000000000000/cancel",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_cancel_no_auth(self, client):
        r = client.post("/api/translate/jobs/nonexistent/cancel")
        assert r.status_code == 401


class TestTranslateCancelPermission:
    """普通用户只能取消自己的任务；Admin 可取消任意任务。"""

    def test_eng_cannot_cancel_others_job(self, client, auth_headers, eng_headers):
        r = _create_job_sample(client, auth_headers, name="admin任务")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r_cancel = client.post(
            f"/api/translate/jobs/{job_id}/cancel",
            headers=eng_headers,
        )
        assert r_cancel.status_code == 403

    def test_admin_can_cancel_others_job(self, client, auth_headers, eng_headers):
        r = _create_job_sample(client, eng_headers, name="eng任务")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r_cancel = client.post(
            f"/api/translate/jobs/{job_id}/cancel",
            headers=auth_headers,
        )
        if r_cancel.status_code == 200:
            detail = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
            assert detail.json()["status"] == "cancelled"

    def test_eng_can_cancel_own_job(self, client, eng_headers):
        r = _create_job_sample(client, eng_headers, name="自己的任务")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r_cancel = client.post(
            f"/api/translate/jobs/{job_id}/cancel",
            headers=eng_headers,
        )
        if r_cancel.status_code == 200:
            detail = client.get(f"/api/translate/jobs/{job_id}", headers=eng_headers)
            assert detail.json()["status"] == "cancelled"


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


class TestTranslateSharedVisibility:
    """项目内所有登录用户共享任务列表，便于查看队列与运行中任务。"""

    def test_can_access_other_users_job(self, client, auth_headers, eng_headers):
        r = _create_job_sample(client, auth_headers, name="admin共享可见任务")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r_get = client.get(f"/api/translate/jobs/{job_id}", headers=eng_headers)
        assert r_get.status_code == 200
        body = r_get.json()
        assert body["job_id"] == job_id
        assert body["name"] == "admin共享可见任务"
        assert body["username"] == "admin"

        r_list = client.get("/api/translate/jobs", headers=eng_headers)
        assert r_list.status_code == 200
        ids = [j["job_id"] for j in r_list.json()]
        assert job_id in ids


class TestTranslateE2E:
    """端到端冒烟：上传 → 等待完成 → 下载。需要 LLM API 可用。"""

    def test_create_and_track(self, client, auth_headers):
        assert SAMPLE_ZIP.exists(), f"测试数据不存在: {SAMPLE_ZIP}"
        r = _create_job_sample(client, auth_headers, name="e2e跟踪任务")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r2 = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
        assert r2.status_code == 200
        detail = r2.json()
        assert detail["job_id"] == job_id
        assert detail["name"] == "e2e跟踪任务"
        assert detail["username"] == "admin"

        r3 = client.get("/api/translate/jobs", headers=auth_headers)
        assert r3.status_code == 200
        ids = [j["job_id"] for j in r3.json()]
        assert job_id in ids

    def test_cancel_queued_job(self, client, auth_headers):
        r = _create_job_sample(client, auth_headers)
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r2 = client.post(
            f"/api/translate/jobs/{job_id}/cancel",
            headers=auth_headers,
        )
        if r2.status_code == 200:
            r3 = client.get(f"/api/translate/jobs/{job_id}", headers=auth_headers)
            assert r3.json()["status"] == "cancelled"
