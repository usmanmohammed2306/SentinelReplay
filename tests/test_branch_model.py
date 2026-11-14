"""Live-model transport keeps remote configuration, budgets and failures explicit."""

from typing import Any

import pytest

from sentinel_replay.branch_model import LoopbackChatModel
from sentinel_replay.canonical import event_digest
from sentinel_replay.isolated_branch import BranchError


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.example.com",
        "http://127.0.0.1@evil.test",
        "http://localhost/v1",
        "http://localhost/?token=x",
    ],
)
def test_model_adapter_rejects_unreviewed_remote_or_ambiguous_endpoint(endpoint: str) -> None:
    with pytest.raises(BranchError):
        LoopbackChatModel(
            endpoint=endpoint, model="test", revision="pinned", task="synthetic", seed=11
        )


def test_model_budget_stops_before_another_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200

        def read(self, limit: int) -> bytes:
            return (
                b'{"choices":[{"message":{"content":"{\\"tool\\":\\"finish\\"}"}}],'
                b'"usage":{"total_tokens":7}}'
            )

    class Connection:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def request(self, *args: Any, **kwargs: Any) -> None:
            pass

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr("sentinel_replay.branch_model.http.client.HTTPConnection", Connection)
    model = LoopbackChatModel(
        endpoint="http://127.0.0.1:18767",
        model="test",
        revision="pinned",
        task="synthetic",
        seed=11,
        max_calls=1,
    )
    assert model.next_action(0, {"state": "ready"}) == {"tool": "finish"}
    assert model.mode == "EXPLORATORY_BRANCH"
    assert len(model.records) == 1
    assert event_digest(model.records).startswith("sha256:")
    with pytest.raises(BranchError, match="budget"):
        model.next_action(1, {})
