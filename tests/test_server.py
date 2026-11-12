import time

import pytest
import video_fixtures as vf
from audio_fixtures import recording, write_wav
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from realis.audio import io
from realis.server import create_app

needs_ffmpeg = pytest.mark.skipif(not io.available(), reason="FFmpeg not installed")


@pytest.fixture
def web_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div><script src=/assets/app.js></script>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    return dist


@pytest.fixture
def client(tmp_path, web_dist):
    app = create_app(tmp_path / "cases", exclude=["trufor"], warmup=False, web_dist=web_dist, max_upload_mb=2)
    with TestClient(app) as c:
        yield c


def wait_for(client, job_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish")


# --- app shell ---------------------------------------------------------------

def test_spa_routes_and_assets(client):
    assert "id=root" in client.get("/").text
    assert "id=root" in client.get("/case/CASE-1").text  # client-side route
    assert client.get("/assets/app.js").text == "console.log('app')"
    assert client.get("/api/nope").status_code == 404


def test_not_built_page(tmp_path):
    app = create_app(tmp_path / "cases", warmup=False, web_dist=tmp_path / "missing")
    with TestClient(app) as c:
        assert "Frontend not built" in c.get("/").text


def test_health(client):
    h = client.get("/api/health").json()
    assert h["runtime"]["device"] in ("cuda", "cpu")
    assert h["models"]["trufor"]["enabled"] is False
    assert {"image", "audio", "video"} == set(h["supported_types"])
    assert ".mp4" in h["supported_types"]["video"] and h["limits"]["max_upload_mb"] == 2
    names = {a["name"] for a in h["analyzers"]}
    assert {"ai_generated", "synthetic_voice", "frame_ai", "temporal_edits"} <= names
    assert next(a for a in h["analyzers"] if a["name"] == "frame_trufor")["deep"] is True


# --- jobs ----------------------------------------------------------------------

def test_image_job_end_to_end(client, coffee):
    r = client.post("/api/jobs", files={"file": ("holiday photo.jpg", jpeg_bytes(coffee, 90), "image/jpeg")})
    assert r.status_code == 202
    job = wait_for(client, r.json()["id"])
    assert job["status"] == "done", job
    report, urls = job["result"]["report"], job["result"]["urls"]
    assert report["evidence"]["original_name"] == "holiday photo.jpg"
    assert report["integrity_verified"] and report["custody_log_valid"]
    assert client.get(urls["evidence"]).status_code == 200
    assert client.get(urls["html"]).status_code == 200
    for per_analyzer in urls["artifacts"].values():
        for url in per_analyzer.values():
            assert client.get(url).headers["content-type"] == "image/png"

    cases = client.get("/api/cases").json()
    assert cases[0]["case_id"] == report["evidence"]["case_id"] and cases[0]["modality"] == "image"
    assert cases[0]["thumbnail"] == urls["evidence"]
    assert client.get("/api/cases?q=holiday").json() and not client.get("/api/cases?q=zzz").json()
    case = client.get(f"/api/cases/{cases[0]['case_id']}").json()
    assert case["items"][0]["report"]["evidence"]["sha256"] == report["evidence"]["sha256"]


def test_job_error_is_reported(client):
    r = client.post("/api/jobs", files={"file": ("fake.jpg", b"not really a jpeg", "image/jpeg")})
    job = wait_for(client, r.json()["id"])
    assert job["status"] == "error" and "not a decodable image" in job["error"]


@needs_ffmpeg
def test_video_job_with_range_requests(client, tmp_path):
    path = vf.with_cut(tmp_path / "clip.mp4", at=3)
    r = client.post("/api/jobs", files={"file": ("clip.mp4", path.read_bytes(), "video/mp4")},
                    data={"deep": "false"})
    job = wait_for(client, r.json()["id"])
    assert job["status"] == "done", job
    report, urls = job["result"]["report"], job["result"]["urls"]
    assert report["modality"] == "video" and not job["deep"]
    temporal = next(x for x in report["results"] if x["analyzer"] == "temporal_edits")
    assert temporal["data"]["cuts"] == [3.0]
    assert client.get(urls["overview"]["Evidence timeline"]).status_code == 200
    partial = client.get(urls["evidence"], headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206 and len(partial.content) == 100  # video seeking
    assert client.get("/api/cases").json()[0]["thumbnail"].endswith(".jpg")


def test_unknown_job_and_case(client):
    assert client.get("/api/jobs/doesnotexist").status_code == 404
    assert client.get("/api/cases/NOPE").status_code == 404
    assert client.get("/api/cases/..%2F..").status_code == 404


# --- synchronous endpoint and upload limits ---------------------------------

@needs_ffmpeg
def test_sync_audio_analysis(client, tmp_path):
    src = tmp_path / "voice.wav"
    write_wav(src, recording(seconds=25))
    r = client.post("/api/analyze", files={"file": ("voice note.wav", src.read_bytes(), "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["report"]["modality"] == "audio"
    assert client.get(r.json()["urls"]["overview"]["Evidence timeline"]).status_code == 200


def test_upload_limits(client):
    assert client.post("/api/jobs", files={"file": ("notes.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post("/api/jobs", files={"file": ("e.png", b"", "image/png")}).status_code == 400
    big = b"\0" * (2 * 1024 * 1024 + 1)
    assert client.post("/api/jobs", files={"file": ("big.mp4", big, "video/mp4")}).status_code == 413


# --- hosted deployment: access code, CORS, retention ----------------------------

@pytest.fixture
def locked(tmp_path, web_dist):
    app = create_app(tmp_path / "cases", warmup=False, web_dist=web_dist, access_code="s3cret",
                     cors_origins=["https://realis.vercel.app"])
    with TestClient(app) as c:
        yield c


def test_access_code_protects_api_and_files(locked, coffee):
    assert locked.get("/api/health").json()["auth_required"] is True  # health stays open
    assert locked.get("/api/cases").status_code == 401
    assert locked.get("/api/cases", headers={"X-Access-Code": "wrong"}).status_code == 401
    ok = {"X-Access-Code": "s3cret"}
    r = locked.post("/api/analyze", headers=ok,
                    files={"file": ("a.jpg", jpeg_bytes(coffee, 90), "image/jpeg")}, data={"deep": "false"})
    assert r.status_code == 200, r.text
    evidence = r.json()["urls"]["evidence"]
    assert locked.get(evidence).status_code == 401
    first = locked.get(evidence + "?key=s3cret")  # media elements cannot send headers
    assert first.status_code == 200 and "realis_key" in first.headers.get("set-cookie", "")


def test_cookie_lets_the_html_report_load_its_images(tmp_path, web_dist, coffee):
    # TestClient is plain http, so the Secure cookie is not resent: check the cookie path directly.
    app = create_app(tmp_path / "cases", warmup=False, web_dist=web_dist, access_code="s3cret")
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/api/analyze", headers={"X-Access-Code": "s3cret"},
                   files={"file": ("a.jpg", jpeg_bytes(coffee, 90), "image/jpeg")})
        html = r.json()["urls"]["html"]
        assert c.get(html + "?key=s3cret").status_code == 200
        assert c.get(r.json()["urls"]["evidence"]).status_code == 200  # cookie only


def test_cors_allows_only_the_configured_site(locked):
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-access-code"}
    ok = locked.options("/api/jobs", headers={"Origin": "https://realis.vercel.app", **pre})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://realis.vercel.app"
    bad = locked.options("/api/jobs", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers
    denied = locked.get("/api/cases", headers={"Origin": "https://realis.vercel.app"})
    assert denied.status_code == 401 and denied.headers["access-control-allow-origin"] == "https://realis.vercel.app"


def test_retention_deletes_old_cases(tmp_path):
    import os
    import stat
    import time

    from realis.cases import prune

    old, fresh = tmp_path / "CASE-old", tmp_path / "CASE-new"
    for case in (old, fresh):
        (case / "evidence").mkdir(parents=True)
        f = case / "evidence" / "x.jpg"
        f.write_bytes(b"x")
        os.chmod(f, stat.S_IREAD)  # evidence is read-only
    past = time.time() - 7200
    os.utime(old, (past, past))
    assert prune(tmp_path, max_age_hours=1) == 1
    assert not old.exists() and fresh.exists()
    assert prune(tmp_path, max_age_hours=0) == 0  # disabled
