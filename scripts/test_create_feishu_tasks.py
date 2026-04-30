"""create_feishu_tasks 单测."""

from __future__ import annotations

import json
import re

import responses

import create_feishu_tasks

_BITABLE_URL_RE = re.compile(
    r"https://open\.feishu\.cn/open-apis/bitable/v1/apps/.+/tables/.+/records"
)


def _mock_bitable_record(record_id: str):
    """注册一个 bitable record create 的 mock, 返回指定 record_id."""
    responses.add(
        responses.POST,
        _BITABLE_URL_RE,
        json={"code": 0, "data": {"record": {"record_id": record_id}}},
    )


def _mock_bitable_fail():
    """注册一个 bitable record create 失败的 mock."""
    responses.add(
        responses.POST,
        _BITABLE_URL_RE,
        json={"code": 1234, "msg": "permission denied"},
    )


def _set_required_env(monkeypatch, issue: str = "42"):
    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("ISSUE_NUMBER", issue)
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "bitable-app")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl-123")


@responses.activate
def test_create_tasks_writes_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        create_feishu_tasks, "TASKS_JSON_PATH", tmp_path / ".planning" / "tasks.json"
    )

    # mock token
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    _mock_bitable_record("rec-1")
    _mock_bitable_record("rec-2")

    _set_required_env(monkeypatch, "42")
    monkeypatch.setenv(
        "ACTION_ITEMS_JSON",
        json.dumps(
            [
                {
                    "title": "实现登录",
                    "description": "",
                    "assignee_name": "张三",
                    "due_date": "2026-04-30",
                },
                {
                    "title": "写文档",
                    "description": "API 文档",
                    "assignee_name": "李四",
                    "due_date": None,
                },
            ]
        ),
    )

    rc = create_feishu_tasks.main()
    assert rc == 0

    mapping = json.loads((tmp_path / ".planning/tasks.json").read_text())
    assert "issue#42" in mapping
    assert len(mapping["issue#42"]) == 2
    assert mapping["issue#42"][0]["record_id"] == "rec-1"
    assert mapping["issue#42"][1]["title"] == "写文档"


def test_no_items_returns_zero(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_ITEMS_JSON", "[]")
    monkeypatch.setenv("FEISHU_APP_ID", "x")
    monkeypatch.setenv("FEISHU_APP_SECRET", "y")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    assert create_feishu_tasks.main() == 0


def test_invalid_json_returns_2(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_ITEMS_JSON", "not json {{{")
    assert create_feishu_tasks.main() == 2


def test_missing_secrets_returns_2(monkeypatch) -> None:
    monkeypatch.setenv("ACTION_ITEMS_JSON", json.dumps([{"title": "x"}]))
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv("ISSUE_NUMBER", raising=False)
    assert create_feishu_tasks.main() == 2


@responses.activate
def test_due_date_with_explicit_tz_is_preserved(tmp_path, monkeypatch) -> None:
    """due_date 含时区不应被覆盖成 UTC."""
    from datetime import datetime

    monkeypatch.setattr(
        create_feishu_tasks, "TASKS_JSON_PATH", tmp_path / ".planning" / "tasks.json"
    )
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )

    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.body)
        return (200, {}, json.dumps({"code": 0, "data": {"record": {"record_id": "rec-1"}}}))

    responses.add_callback(
        responses.POST,
        _BITABLE_URL_RE,
        callback=handler,
    )

    _set_required_env(monkeypatch, "1")
    # +08:00 时区, 不应被覆盖成 UTC
    monkeypatch.setenv(
        "ACTION_ITEMS_JSON",
        json.dumps([{"title": "x", "due_date": "2026-04-30T10:00:00+08:00"}]),
    )
    assert create_feishu_tasks.main() == 0
    body = captured["body"]
    expected_ts_ms = int(datetime.fromisoformat("2026-04-30T10:00:00+08:00").timestamp() * 1000)
    assert int(body["fields"]["预计交付日期"]) == expected_ts_ms


def test_invalid_action_items_filtered_by_pydantic(tmp_path, monkeypatch) -> None:
    """ACTION_ITEMS_JSON 里非法 item 应被 pydantic 过滤掉, 全非法时返 0 不调外部."""
    monkeypatch.setenv(
        "ACTION_ITEMS_JSON",
        json.dumps(
            [
                {"title": ""},  # 空 title 不合法 (min_length=1)
                "not a dict",  # 非 dict 直接跳
                {"title": "x" * 500},  # title 超 200 字符不合法
            ]
        ),
    )
    monkeypatch.setenv("FEISHU_APP_ID", "x")
    monkeypatch.setenv("FEISHU_APP_SECRET", "y")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    # 全部不合法 -> 走"没有合法 action items"早退分支, 不调任何 API
    assert create_feishu_tasks.main() == 0


@responses.activate
def test_one_failed_task_does_not_abort_batch(tmp_path, monkeypatch) -> None:
    """单条 item 创建失败不应让整批失败."""
    monkeypatch.setattr(
        create_feishu_tasks, "TASKS_JSON_PATH", tmp_path / ".planning" / "tasks.json"
    )

    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    _mock_bitable_record("rec-ok")
    _mock_bitable_fail()
    _mock_bitable_record("rec-ok2")

    _set_required_env(monkeypatch, "1")
    monkeypatch.setenv(
        "ACTION_ITEMS_JSON",
        json.dumps(
            [
                {"title": "ok-1"},
                {"title": "fail"},
                {"title": "ok-2"},
            ]
        ),
    )

    rc = create_feishu_tasks.main()
    assert rc == 0

    mapping = json.loads((tmp_path / ".planning/tasks.json").read_text())
    # 只有 2 条成功的入了映射
    assert len(mapping["issue#1"]) == 2
    assert {c["record_id"] for c in mapping["issue#1"]} == {"rec-ok", "rec-ok2"}


@responses.activate
def test_cross_issue_dedup(tmp_path, monkeypatch) -> None:
    """已在其他 issue 创建过的同名任务应被跳过."""
    tasks_json = tmp_path / ".planning" / "tasks.json"
    tasks_json.parent.mkdir(parents=True)
    tasks_json.write_text(
        json.dumps(
            {
                "issue#10": [
                    {
                        "record_id": "rec-old",
                        "title": "重复任务",
                        "assignee_name": "张三",
                        "due_date": None,
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(create_feishu_tasks, "TASKS_JSON_PATH", tasks_json)

    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    _mock_bitable_record("rec-new")

    _set_required_env(monkeypatch, "20")
    monkeypatch.setenv(
        "ACTION_ITEMS_JSON",
        json.dumps(
            [
                {"title": "重复任务"},  # 已存在于 issue#10, 应跳过
                {"title": "新任务"},  # 新的, 应创建
            ]
        ),
    )

    rc = create_feishu_tasks.main()
    assert rc == 0

    mapping = json.loads(tasks_json.read_text())
    # issue#20 只有新任务, 重复的被跳过
    assert len(mapping["issue#20"]) == 1
    assert mapping["issue#20"][0]["title"] == "新任务"
    # issue#10 保持不变
    assert len(mapping["issue#10"]) == 1
