import json
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from app import demo_server as demo


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(demo, "DEFAULT_OUT_DIR", tmp_path / "repairs")
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline mode must not launch an AGH/model process")
    monkeypatch.setattr(demo.subprocess, "Popen", forbidden)
    instance = demo.DemoServer(("127.0.0.1", 0), "offline")
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{instance.server_port}"
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=3)


def open_local(url, data=None):
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    return build_opener(ProxyHandler({})).open(request, timeout=20)


@pytest.mark.integration
def test_offline_http_upload_and_sse_complete_without_model(server):
    with open_local(server + "/api/health") as response:
        assert json.load(response)["mode"] == "offline"
    with open_local(server + "/api/sample?name=sensor_bearing_wear.csv") as response:
        csv = response.read().decode("utf-8")
    with open_local(server + "/api/upload", json.dumps({"name": "bearing.csv", "csv": csv}).encode()) as response:
        uploaded = json.load(response)["file"]
    events = []
    with open_local(server + "/api/run?file=" + uploaded) as response:
        for line in response:
            if line.startswith(b"data: "):
                event = json.loads(line[6:])
                events.append(event)
                if event["type"] == "done":
                    break
    assert (events[-1]["type"], events[-1]["ok"], events[-1]["mode"]) == ("done", True, "offline")
    assert any(e["type"] == "verify" and e["status"] == "success" for e in events)
    assert not any(e["type"] == "error" for e in events)


@pytest.mark.integration
@pytest.mark.parametrize("payload", [b"not-json", b"[]", b'{"csv":""}'])
def test_invalid_upload_returns_client_error(server, payload):
    with pytest.raises(HTTPError) as error:
        open_local(server + "/api/upload", payload)
    assert error.value.code == 400


@pytest.mark.integration
def test_sample_cannot_read_files_outside_data(server):
    with pytest.raises(HTTPError) as error:
        open_local(server + "/api/sample?name=..%2FREADME.md")
    assert error.value.code == 404


def test_tool_error_ends_job_as_failure(tmp_path):
    job_id = "test-invalid-csv"
    demo._jobs[job_id] = {"events": [], "lock": threading.Lock()}
    try:
        demo.run_job(job_id, tmp_path / "missing.csv")
        events = demo._jobs[job_id]["events"]
        assert events[-1]["type"] == "done" and events[-1]["ok"] is False
        assert any(event["type"] == "error" for event in events)
    finally:
        demo._jobs.pop(job_id)
