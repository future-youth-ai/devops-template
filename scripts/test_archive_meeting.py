"""archive_meeting 单测."""

from __future__ import annotations

import json

import archive_meeting
from archive_meeting import build_table


def test_build_table_empty() -> None:
    assert "未提取到" in build_table([])


def test_build_table_with_items() -> None:
    md = build_table(
        [
            {"title": "登录", "assignee_name": "张三", "due_date": "2026-04-30", "record_id": "g1"},
            {"title": "文档", "assignee_name": "", "due_date": None, "record_id": "g2"},
        ]
    )
    assert "| 1 | 登录 | 张三 | 2026-04-30 | `g1` |" in md
    assert "| 2 | 文档 | 未指派 | — | `g2` |" in md


def test_build_table_escapes_pipe() -> None:
    md = build_table([{"title": "a|b", "assignee_name": "c|d", "due_date": None, "record_id": "g"}])
    assert "a\\|b" in md
    assert "c\\|d" in md


def _patch_paths(tmp_path, monkeypatch) -> tuple:
    """把 archive_meeting 的输出路径都 patch 到 tmp_path 下."""
    tasks_json = tmp_path / ".planning" / "tasks.json"
    meetings_dir = tmp_path / ".planning" / "meetings"
    monkeypatch.setattr(archive_meeting, "TASKS_JSON_PATH", tasks_json)
    monkeypatch.setattr(archive_meeting, "MEETINGS_DIR", meetings_dir)
    return tasks_json, meetings_dir


def test_main_writes_file(tmp_path, monkeypatch, capsys) -> None:
    tasks_json, meetings_dir = _patch_paths(tmp_path, monkeypatch)
    tasks_json.parent.mkdir(parents=True)
    tasks_json.write_text(
        json.dumps(
            {
                "issue#99": [
                    {
                        "title": "测试任务",
                        "assignee_name": "张三",
                        "due_date": "2026-05-01",
                        "record_id": "g-1",
                    }
                ]
            }
        )
    )

    monkeypatch.setenv("MEETING_TITLE", "测试会议")
    monkeypatch.setenv("MEETING_DATE", "2026-04-23")
    monkeypatch.setenv("ISSUE_NUMBER", "99")
    monkeypatch.setenv("FEISHU_URL", "https://meetings.feishu.cn/minutes/xxx")

    rc = archive_meeting.main()
    assert rc == 0

    out = meetings_dir / "2026-04-23-issue99.md"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# 测试会议" in content
    assert "**入口 issue**: #99" in content
    assert "https://meetings.feishu.cn/minutes/xxx" in content
    assert "| 1 | 测试任务 | 张三 | 2026-05-01 | `g-1` |" in content

    # stdout 含文件路径供 workflow 拿
    captured = capsys.readouterr()
    assert "2026-04-23-issue99.md" in captured.out


def test_main_no_tasks_json(tmp_path, monkeypatch) -> None:
    """tasks.json 不存在时归档仍能跑, 表格区为空提示."""
    _, meetings_dir = _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("MEETING_TITLE", "空会议")
    monkeypatch.setenv("MEETING_DATE", "2026-04-23")
    monkeypatch.setenv("ISSUE_NUMBER", "1")

    rc = archive_meeting.main()
    assert rc == 0

    out = meetings_dir / "2026-04-23-issue1.md"
    assert out.exists()
    assert "未提取到" in out.read_text(encoding="utf-8")


def test_main_rejects_path_traversal_in_date(tmp_path, monkeypatch) -> None:
    """MEETING_DATE 含 ../ 等穿越片段必须被拒."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("MEETING_DATE", "../../etc/passwd")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    assert archive_meeting.main() == 2


def test_main_rejects_non_numeric_issue(tmp_path, monkeypatch) -> None:
    """ISSUE_NUMBER 必须纯数字."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("MEETING_DATE", "2026-04-23")
    monkeypatch.setenv("ISSUE_NUMBER", "../../99")
    assert archive_meeting.main() == 2


def test_main_handles_dirty_tasks_json(tmp_path, monkeypatch) -> None:
    """tasks.json 里如果某 issue 的值不是 list, 或 list 内有非 dict, 不能崩."""
    tasks_json, meetings_dir = _patch_paths(tmp_path, monkeypatch)
    tasks_json.parent.mkdir(parents=True)
    tasks_json.write_text(
        json.dumps(
            {
                "issue#1": "not a list",  # 错: 应该是 list
                "issue#2": [
                    {"title": "ok", "record_id": "g1", "assignee_name": "x", "due_date": None},
                    "not a dict",  # 错: list 内有非 dict
                ],
            }
        )
    )
    monkeypatch.setenv("MEETING_DATE", "2026-04-23")
    monkeypatch.setenv("ISSUE_NUMBER", "2")

    rc = archive_meeting.main()
    assert rc == 0

    out = meetings_dir / "2026-04-23-issue2.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    # 只有合法的 dict 入了表格
    assert "| 1 | ok | x" in text
    assert "not a dict" not in text
