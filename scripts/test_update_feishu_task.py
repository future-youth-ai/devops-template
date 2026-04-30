"""update_feishu_task 单测."""

from __future__ import annotations

import json
import re

import responses

import update_feishu_task

_BITABLE_RECORD_URL_RE = re.compile(
    r"https://open\.feishu\.cn/open-apis/bitable/v1/apps/.+/tables/.+/records/.+"
)


def test_no_task_tag_in_message_skips(monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_MESSAGE", "feat: 普通提交")
    assert update_feishu_task.main() == 0


def test_no_message_skips(monkeypatch) -> None:
    monkeypatch.delenv("COMMIT_MESSAGE", raising=False)
    assert update_feishu_task.main() == 0


def test_done_tag_but_missing_secrets(monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_MESSAGE", "fix: x [DONE-TASK-abc]")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    assert update_feishu_task.main() == 0  # warning 但不 fail


@responses.activate
def test_done_tag_calls_update(monkeypatch) -> None:
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    responses.add(
        responses.PUT,
        _BITABLE_RECORD_URL_RE,
        json={"code": 0, "data": {}},
    )

    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "bitable-app")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl-123")
    # record_id 直接从 tag 取, 不再走 tasks.json
    monkeypatch.setenv("COMMIT_MESSAGE", "fix: 修 bug [DONE-TASK-recABC123]")

    assert update_feishu_task.main() == 0
    assert len(responses.calls) == 2  # token + PUT


@responses.activate
def test_non_done_tag_updates_to_developing(monkeypatch) -> None:
    """普通 [TASK-xxx] 应更新状态为 '开发中'."""
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )

    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.body)
        return (200, {}, json.dumps({"code": 0, "data": {}}))

    responses.add_callback(
        responses.PUT,
        _BITABLE_RECORD_URL_RE,
        callback=handler,
    )

    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "bitable-app")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl-123")
    monkeypatch.setenv("COMMIT_MESSAGE", "feat: 进行中 [TASK-rec-abc]")

    assert update_feishu_task.main() == 0
    assert len(responses.calls) == 2  # token + PUT
    assert captured["body"]["fields"]["进展状态"] == "开发中"


@responses.activate
def test_multiple_tasks_in_one_commit(monkeypatch) -> None:
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    responses.add(
        responses.PUT,
        _BITABLE_RECORD_URL_RE,
        json={"code": 0, "data": {}},
    )
    responses.add(
        responses.PUT,
        _BITABLE_RECORD_URL_RE,
        json={"code": 0, "data": {}},
    )

    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "bitable-app")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl-123")
    monkeypatch.setenv(
        "COMMIT_MESSAGE",
        "feat: 完成两件事 [DONE-TASK-rec-one] [DONE-TASK-rec-two]",
    )

    assert update_feishu_task.main() == 0
    assert len(responses.calls) == 3  # token + 2 PUT


@responses.activate
def test_api_failure_returns_1(monkeypatch) -> None:
    """飞书 API 返回错误时 failures += 1, 最终返回 1."""
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    responses.add(
        responses.PUT,
        _BITABLE_RECORD_URL_RE,
        json={"code": 1234, "msg": "not found"},
    )

    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "bitable-app")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl-123")
    monkeypatch.setenv("COMMIT_MESSAGE", "fix: x [DONE-TASK-nonexistent]")

    assert update_feishu_task.main() == 1
