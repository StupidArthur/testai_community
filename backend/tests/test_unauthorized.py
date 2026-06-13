"""认证回归测试：缺凭证统一 401。"""


class TestUnauthorized:
    def test_jobs_no_auth(self, client):
        r = client.get("/api/translate/jobs")
        assert r.status_code == 401

    def test_create_job_no_auth(self, client):
        r = client.post("/api/translate/jobs")
        assert r.status_code in (401, 422)

    def test_get_job_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent")
        assert r.status_code == 401

    def test_cancel_job_no_auth(self, client):
        r = client.post("/api/translate/jobs/nonexistent/cancel")
        assert r.status_code == 401

    def test_stream_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/stream")
        assert r.status_code == 401

    def test_download_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/download")
        assert r.status_code == 401

    def test_ticket_no_auth(self, client):
        r = client.post("/api/translate/ticket")
        assert r.status_code == 401

    def test_prompts_no_auth(self, client):
        r = client.get("/api/translate/prompts")
        assert r.status_code == 401

    def test_delete_record_no_auth(self, client):
        r = client.delete("/api/translate/jobs/nonexistent/record")
        assert r.status_code == 401

    def test_changelog_no_auth(self, client):
        r = client.get("/api/changelog")
        assert r.status_code == 401

    def test_skills_no_auth(self, client):
        r = client.get("/api/skills")
        assert r.status_code == 401


class TestOldPathsRemoved:
    def test_old_translate_api_jobs(self, client):
        r = client.get("/translate/api/jobs")
        assert r.status_code != 200 or "text/html" in r.headers.get("content-type", "")

    def test_old_upload_path_removed(self, client):
        r = client.post("/api/translate/upload")
        assert r.status_code in (404, 405)

    def test_old_cancel_delete_removed(self, client):
        r = client.delete("/api/translate/jobs/nonexistent")
        assert r.status_code in (404, 405)

    def test_old_file_preview_removed(self, client):
        r = client.get("/api/translate/jobs/nonexistent/file?p=test.md")
        assert r.status_code in (404, 405)
