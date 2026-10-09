from app.services.pdf_report import pdf_text
from tests.helpers import ai_json


def pdf_url(analysis_id) -> str:
    return f"/api/analyses/{analysis_id}/pdf"


def test_pdf_download_returns_a_real_pdf(client, analyze, headers_a):
    created = analyze().json()
    r = client.get(pdf_url(created["id"]), headers=headers_a)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f"deploydoctor-diagnosis-{created['id']}-" in disposition
    assert r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"%PDF-")
    assert b"%%EOF" in r.content[-1024:]
    assert len(r.content) > 2000


def test_another_session_cannot_download_the_pdf(client, analyze, headers_b):
    created = analyze().json()
    assert client.get(pdf_url(created["id"]), headers=headers_b).status_code == 404


def test_pdf_requires_a_session_header_and_a_known_id(client, analyze, headers_a):
    created = analyze().json()
    assert client.get(pdf_url(created["id"])).status_code == 400
    assert client.get(pdf_url(999999), headers=headers_a).status_code == 404
    assert client.get("/api/analyses/not-a-number/pdf", headers=headers_a).status_code == 422


def test_markup_and_unusual_characters_do_not_break_the_report(client, analyze, fake_ai, headers_a):
    nasty = '<img src="file:///etc/passwd"> & <b>unclosed <para> </para> </font>'
    fake_ai.push(
        ai_json(
            summary=nasty,
            root_cause=nasty,
            affected_component=nasty,
            evidence=[],
            recommended_fix=[nasty],
            commands=[nasty, "x" * 450, "tab\tand  spaces\nnew line  │ ─ → नमस्ते"],
            prevention=[nasty, "देवऑप्स"],
            devops_insight=nasty,
        )
    )
    created = analyze().json()
    r = client.get(pdf_url(created["id"]), headers=headers_a)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_long_reports_still_build(client, analyze, fake_ai, headers_a):
    fake_ai.push(
        ai_json(
            recommended_fix=["step " + "word " * 90] * 10,
            commands=["cmd " + "x" * 440] * 12,
            prevention=["prevent " + "word " * 80] * 8,
        )
    )
    created = analyze().json()
    r = client.get(pdf_url(created["id"]), headers=headers_a)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_a_fallback_result_can_be_downloaded(client, analyze, fake_ai, headers_a):
    fake_ai.push("not json", "still not json")
    created = analyze().json()
    assert created["degraded"] is True
    r = client.get(pdf_url(created["id"]), headers=headers_a)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_pdf_downloads_are_rate_limited(client, analyze, headers_a):
    created = analyze().json()
    codes = [client.get(pdf_url(created["id"]), headers=headers_a).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_pdf_text_maps_and_replaces_characters():
    assert pdf_text("a│b ─ → c") == "a|b - -> c"
    assert set(pdf_text("नमस्ते")) == {"?"}
    assert pdf_text("a\x00b\x07c") == "abc"
    assert pdf_text(None) == ""
    assert pdf_text("café “quoted” …") == "café “quoted” …"
    assert pdf_text("one\r\ntwo\rthree") == "one\ntwo\nthree"
