import pytest


def upload(client, name, data, content_type="text/plain"):
    return client.post("/api/upload-log", files={"file": (name, data, content_type)})


def test_valid_log_file_is_accepted(client):
    r = upload(client, "app.log", b"ERROR: connection refused\n")
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "app.log"
    assert body["text"] == "ERROR: connection refused"
    assert body["size_bytes"] == 26
    assert body["characters"] == 25


def test_extension_check_is_case_insensitive(client):
    assert upload(client, "APP.LOG", b"ERROR x\n").status_code == 200


@pytest.mark.parametrize("name", ["malware.exe", "notes.pdf", "noextension", "script.sh"])
def test_other_file_types_are_rejected(client, name):
    r = upload(client, name, b"ERROR x\n")
    assert r.status_code == 400


def test_empty_and_blank_files_are_rejected(client):
    assert upload(client, "a.log", b"").status_code == 400
    assert upload(client, "a.log", b"  \n \n").status_code == 400


def test_binary_files_are_rejected(client):
    assert upload(client, "a.log", b"a\x00b").status_code == 400


def test_files_over_the_byte_limit_are_rejected(client):
    assert upload(client, "big.log", b"x" * (1_048_576 + 1)).status_code == 413


def test_text_over_the_character_limit_is_rejected(client):
    assert upload(client, "long.log", b"x" * 60000).status_code == 413


def test_invalid_utf8_is_replaced_not_crashed(client):
    r = upload(client, "a.log", b"ERROR \xff\xfe boom")
    assert r.status_code == 200
    assert "boom" in r.json()["text"]


def test_client_paths_are_reduced_to_a_base_name(client):
    r = upload(client, "../../etc/passwd.log", b"x\n")
    assert r.status_code == 200
    assert "/" not in r.json()["filename"]
    assert r.json()["filename"].endswith("passwd.log")


def test_upload_is_rate_limited(client):
    codes = [upload(client, "a.log", b"ERROR x\n").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limited = upload(client, "a.log", b"ERROR x\n")
    assert limited.headers["retry-after"] == "60"
    assert "Too many requests" in limited.json()["detail"]
