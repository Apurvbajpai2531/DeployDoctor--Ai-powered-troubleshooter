def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["service"] == "DeployDoctor"
    assert body["uptime_seconds"] >= 0
    assert r.headers["x-request-id"]
    assert float(r.headers["x-process-time-ms"]) >= 0


def test_health_reports_degraded_when_database_is_down(client, monkeypatch):
    monkeypatch.setattr("app.routes.health.check_database", lambda: False)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == "unavailable"


def test_health_does_not_leak_configuration(client):
    text = client.get("/health").text.lower()
    assert "test-key-not-real" not in text
    assert "sqlite" not in text
    assert "postgres" not in text


def test_root_serves_the_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "DeployDoctor" in r.text


def test_static_assets_are_served(client):
    for path in ("/static/style.css", "/static/app.js", "/static/samples.js"):
        assert client.get(path).status_code == 200, path


def test_openapi_documents_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/health",
        "/api/analyze",
        "/api/analyses",
        "/api/analyses/{analysis_id}",
        "/api/upload-log",
    ):
        assert path in paths, path
