import os
from pathlib import Path
import shutil
import subprocess
import sys
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

import pytest


@pytest.mark.integration
def test_nine_mcp_tools_over_real_stdio_without_api_key(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for directory in ("agent/mcp", "tools", "data"):
        shutil.copytree(root / directory, tmp_path / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "repairs", "uploads"))
    env = {k: v for k, v in os.environ.items() if k != "AGNES_API_KEY"}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(tmp_path / "agent/mcp/verify_mcp_client.py")],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[call]") == 9
    assert "FAILED" not in result.stdout


def test_self_check_returns_failure_when_one_tool_fails(monkeypatch, capsys):
    from agent.mcp import verify_mcp_client as check

    @asynccontextmanager
    async def fake_stdio(*args):
        yield None, None

    class Session:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def initialize(self):
            return SimpleNamespace(server_info=SimpleNamespace(name="test", version="1"), protocol_version="test")
        async def list_tools(self):
            return SimpleNamespace(tools=[])
        async def call_tool(self, name, args):
            payload = {"status": "ok", "output_csv": "fake.csv", "worst_residual_sigma": 0}
            return SimpleNamespace(is_error=name == "run_closed_loop",
                                   content=[SimpleNamespace(text=json.dumps(payload))])

    monkeypatch.setattr(check, "stdio_client", fake_stdio)
    monkeypatch.setattr(check, "ClientSession", Session)
    assert asyncio.run(check.main()) == 1
    assert "1/9" in capsys.readouterr().out
