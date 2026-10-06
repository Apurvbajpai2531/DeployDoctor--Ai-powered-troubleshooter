"""Static checks on the frontend files (no browser involved)."""
import re

from app.config import PROJECT_ROOT, get_settings
from app.schemas.analysis import FailureCategory

FRONTEND = PROJECT_ROOT / "frontend"
HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
JS = (FRONTEND / "app.js").read_text(encoding="utf-8")
SAMPLES = (FRONTEND / "samples.js").read_text(encoding="utf-8")
JS_CODE = re.sub(r"/\*.*?\*/", "", JS, flags=re.DOTALL)  # comments may mention banned APIs


def test_page_basics():
    assert '<html lang="en">' in HTML
    assert 'name="viewport"' in HTML
    assert "<title>DeployDoctor" in HTML
    assert "Turn confusing logs into clear fixes." in HTML
    assert "Find the failure. Understand the cause. Fix the deployment." in HTML


def test_every_element_id_used_by_the_script_exists_in_the_page():
    html_ids = set(re.findall(r'\bid="([^"]+)"', HTML))
    used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', JS_CODE))
    assert used, "no element lookups found; the pattern is probably stale"
    assert used - html_ids == set()


def test_category_dropdown_matches_the_backend_enum():
    options = re.findall(r'<option value="([^"]+)"', HTML)
    assert sorted(options) == sorted(c.value for c in FailureCategory)


def test_client_side_limits_match_the_server_limits():
    settings = get_settings()
    assert int(re.search(r"const MAX_LOG_CHARS = (\d+);", JS).group(1)) == settings.max_log_chars
    assert int(re.search(r"const MAX_UPLOAD_BYTES = (\d+);", JS).group(1)) == settings.max_upload_bytes


def test_script_never_builds_html_from_strings():
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in JS_CODE, banned


def test_page_is_compatible_with_the_strict_csp():
    for tag in re.findall(r"<script\b[^>]*>", HTML):
        assert "src=" in tag, f"inline script: {tag}"
    assert "<style" not in HTML
    assert not re.search(r"\sstyle\s*=", HTML)
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", HTML)


def test_samples_load_before_the_app_script():
    assert HTML.index("/static/samples.js") < HTML.index("/static/app.js")


def test_sample_logs_are_complete_and_valid():
    ids = re.findall(r'\bid: "([^"]+)"', SAMPLES)
    categories = re.findall(r'category: "([^"]+)"', SAMPLES)
    assert len(ids) == len(set(ids)) == 7
    assert {"docker", "kubernetes", "aws", "terraform", "cicd", "postgres", "nginx"} == set(ids)
    assert set(categories) <= {c.value for c in FailureCategory}
