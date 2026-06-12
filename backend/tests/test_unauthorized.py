"""认证回归测试：确保所有 translate 路由都需要认证。"""


class TestUnauthorized:
    def test_jobs_no_auth(self, client):
        r = client.get("/api/translate/jobs")
        assert r.status_code == 401

    def test_upload_no_auth(self, client):
        r = client.post("/api/translate/upload")
        assert r.status_code == 401

    def test_get_job_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent")
        assert r.status_code == 401

    def test_cancel_job_no_auth(self, client):
        r = client.delete("/api/translate/jobs/nonexistent")
        assert r.status_code == 401

    def test_stream_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/stream")
        assert r.status_code == 401

    def test_download_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/download")
        assert r.status_code == 401

    def test_file_no_auth(self, client):
        r = client.get("/api/translate/jobs/nonexistent/file?p=test.md")
        assert r.status_code == 401

    def test_ticket_no_auth(self, client):
        r = client.post("/api/translate/ticket")
        assert r.status_code == 401


class TestOldPathsRemoved:
    def test_old_translate_api_jobs(self, client):
        r = client.get("/translate/api/jobs")
        assert r.status_code != 200 or "text/html" in r.headers.get("content-type", "")

    def test_old_translate_api_upload(self, client):
        r = client.post("/translate/api/upload")
        assert r.status_code in (404, 405) or "text/html" in r.headers.get("content-type", "")
