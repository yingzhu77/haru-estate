"""Sanitized adapter diagnostics with synthetic responses, never live credentials."""

import json

import httpx
import pytest

from app.agent_model import DeepSeekModel, ModelFailure


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "认证失败"), (402, "余额不足"), (403, "访问被拒绝"), (429, "限流"), (503, "未接受请求")],
)
def test_http_failure_does_not_expose_provider_body(status: int, expected: str) -> None:
    model = DeepSeekModel(
        api_key="synthetic-secret",
        model="test-only",
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="synthetic-secret")),
    )
    with pytest.raises(ModelFailure) as exc:
        model.plan("模拟问题", [], {})
    assert expected in str(exc.value)
    assert str(status) in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)


@pytest.mark.parametrize("timeout", [True, False])
def test_network_diagnostics(timeout: bool) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if timeout:
            raise httpx.ReadTimeout("synthetic-secret", request=request)
        raise httpx.ConnectError("synthetic-secret", request=request)

    model = DeepSeekModel(
        api_key="synthetic-secret", model="test-only", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ModelFailure) as exc:
        model.plan("模拟问题", [], {})
    assert ("超时" if timeout else "无法连接") in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            '{"action":"draft","change":{"phase_id":"p","field":"price_change","value":-0.05}}',
            "change.value",
        ),
        ('{"action":"clarify","clarification":"说明","synthetic-secret":"private"}', "格式不符合"),
        ('{"action":"clarify","clarification":""}', "clarification"),
        ('{"action":"query"}', "格式不符合"),
        ("not-json-synthetic-secret", "格式不符合"),
    ],
)
def test_invalid_plan_reports_only_known_fields(content: str, expected: str) -> None:
    model = DeepSeekModel(
        api_key="synthetic-secret",
        model="test-only",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                },
            )
        ),
    )
    with pytest.raises(ModelFailure) as exc:
        model.plan("模拟问题", [], {})
    assert expected in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)
    assert "private" not in str(exc.value)


def test_adapter_accepts_decimal_text_draft_without_computing_price() -> None:
    draft = {
        "action": "draft",
        "change": {
            "phase_id": "phase-1",
            "field": "price_change",
            "value": "-0.05",
        },
    }

    def respond(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["messages"][0]["content"]
        assert "十进制字符串" in prompt
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(draft)},
                    }
                ]
            },
        )

    model = DeepSeekModel(
        api_key="synthetic-secret", model="test-only", transport=httpx.MockTransport(respond)
    )
    plan = model.plan("模拟降价", [], {"mode": "change"})
    assert plan.action == "draft"
    assert plan.change is not None and plan.change.value == "-0.05"


@pytest.mark.parametrize(
    ("failure", "code", "expected"),
    [
        (httpx.ConnectTimeout, "connect_timeout", "连接模型服务超时"),
        (httpx.ReadTimeout, "read_timeout", "等待模型返回数据超时"),
        (httpx.WriteTimeout, "write_timeout", "发送请求超时"),
        (httpx.PoolTimeout, "timeout", "连接资源超时"),
    ],
)
def test_timeout_stage_elapsed_and_no_automatic_retry(
    failure: type[httpx.TimeoutException],
    code: str,
    expected: str,
) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.extensions["timeout"]["connect"] == 10
        assert request.extensions["timeout"]["read"] == 20
        raise failure("synthetic-secret", request=request)

    model = DeepSeekModel(
        api_key="synthetic-secret", model="test-only", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ModelFailure) as exc:
        model.plan("模拟降价", [], {"mode": "change"})
    assert exc.value.code == code
    assert expected in str(exc.value) and "耗时" in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)
    assert len(calls) == 1
