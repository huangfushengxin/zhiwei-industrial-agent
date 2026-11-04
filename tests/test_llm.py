import io
import json
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from agent.llm.client import ChatClient, LLMError
from agent.llm.context import ContextBudgetError
from agent.llm.report import collect_facts, generate_report
from agent.llm.schema import DiagnosticReport


def envelope(content, reason="stop"):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content},
                                             "finish_reason": reason}]}).encode())


def test_http_request_sends_model_authorization_and_output_budget():
    def opener(request, timeout):
        assert request.full_url == "https://example.test/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-only"
        body = json.loads(request.data)
        assert body["model"] == "test-model" and body["max_tokens"] == 512
        assert body["messages"] == [{"role": "user", "content": "facts"}]
        assert timeout == 30
        return envelope("report")
    client = ChatClient("test-only", base_url="https://example.test/v1", model="test-model", opener=opener)
    assert client.complete([{"role": "user", "content": "facts"}], output_tokens=512) == "report"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_failure_is_retried_with_limit(status):
    attempts = []
    def opener(request, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPError(request.full_url, status, "error", {}, io.BytesIO())
        return envelope("ok")
    client = ChatClient("test-only", opener=opener, sleeper=lambda _: None)
    assert client.complete([], output_tokens=512) == "ok"
    assert len(attempts) == 2


def test_auth_error_is_not_retried_or_leaked():
    attempts = []
    def opener(request, timeout):
        attempts.append(1)
        raise HTTPError(request.full_url, 401, "sensitive-key", {}, io.BytesIO(b"private response"))
    with pytest.raises(LLMError, match="HTTP 401") as error:
        ChatClient("sensitive-key", opener=opener).complete([], output_tokens=512)
    assert len(attempts) == 1
    assert "sensitive-key" not in str(error.value) and "private" not in str(error.value)


def test_network_error_exhaustion_is_bounded():
    attempts = []
    def opener(request, timeout):
        attempts.append(1)
        raise URLError("private network details")
    with pytest.raises(LLMError, match="timed out"):
        ChatClient("test-only", opener=opener, sleeper=lambda _: None).complete([], output_tokens=512)
    assert len(attempts) == 2


@pytest.mark.parametrize("response", [lambda: io.BytesIO(b"not json"),
                                       lambda: envelope("partial", "length"),
                                       lambda: envelope(None)])
def test_invalid_or_truncated_envelope_is_rejected(response):
    with pytest.raises(LLMError):
        ChatClient("test-only", opener=lambda *a, **k: response()).complete([], output_tokens=512)


def valid_report(facts):
    return {**{k: facts[k] for k in ("source_file", "status", "fault", "health_index")},
            "summary": "仿真数据存在轴承异常，需复核。", "recommendations": ["检查轴承"],
            "limitations": ["仿真数据，未经现场验证；未执行维修。"]}


class StubClient:
    model = "test-double-no-live-api"
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []
    def complete(self, messages, *, output_tokens):
        self.requests.append(messages)
        return next(self.outputs)


@pytest.fixture
def facts(data_dir):
    return collect_facts(data_dir / "sensor_bearing_wear.csv")


@pytest.mark.parametrize("bad", ["not json", '{"status":"normal"}', "wrong-fault", "extra-field"])
def test_invalid_report_gets_one_correction_attempt(facts, bad):
    good = valid_report(facts)
    if bad == "wrong-fault":
        bad = json.dumps({**good, "fault": "normal"})
    elif bad == "extra-field":
        bad = json.dumps({**good, "repair_succeeded": True})
    client = StubClient([bad, json.dumps(good)])
    result = generate_report(facts, client)
    assert result["validation_attempts"] == 2
    assert result["report"]["fault"] == "bearing_wear"
    assert len(client.requests) == 2


def test_repeated_schema_failure_never_returns_an_unvalidated_report(facts):
    with pytest.raises(LLMError, match="twice"):
        generate_report(facts, StubClient(["invalid", "invalid"]))


def test_over_budget_facts_do_not_make_an_api_request(facts):
    client = StubClient([])
    with pytest.raises(ContextBudgetError):
        generate_report(facts, client, window=1024)
    assert not client.requests


@pytest.mark.parametrize("change", [{"health_index": 101}, {"health_index": "50"},
                                    {"recommendations": []}, {"fault": "invented"}])
def test_report_contract_rejects_invalid_fields(facts, change):
    with pytest.raises(ValidationError):
        DiagnosticReport.model_validate({**valid_report(facts), **change})
