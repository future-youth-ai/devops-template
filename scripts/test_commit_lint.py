"""commit_lint 单测."""

from __future__ import annotations

from commit_lint import validate_subject


# ---------- 主体格式 ----------
def test_conventional_simple() -> None:
    ok, kind = validate_subject("feat: 加一个功能")
    assert ok and kind == "conventional"


def test_conventional_with_scope() -> None:
    ok, kind = validate_subject("fix(api): 修 bug")
    assert ok and kind == "conventional"


def test_deliverable() -> None:
    ok, kind = validate_subject("[DEL-04] 文档解析器完成")
    assert ok and kind == "deliverable"


def test_milestone() -> None:
    ok, kind = validate_subject("[DEL-07][MVP] AI 审核引擎可用")
    assert ok and kind == "deliverable"


def test_phase() -> None:
    ok, kind = validate_subject("[PHASE-1] Phase 1 全部交付完成")
    assert ok and kind == "phase"


def test_merge_allowed() -> None:
    ok, kind = validate_subject("Merge pull request #42 from user/branch")
    assert ok and kind == "merge"


# ---------- TASK 尾标签 ----------
def test_conventional_with_task_tag() -> None:
    ok, kind = validate_subject("feat(api): 实现登录 [TASK-abc123]")
    assert ok and kind == "conventional"


def test_conventional_with_done_task_tag() -> None:
    ok, kind = validate_subject("fix: 修登录 bug [DONE-TASK-abc-123_xyz]")
    assert ok and kind == "conventional"


def test_deliverable_with_task_tag() -> None:
    ok, kind = validate_subject("[DEL-04] 文档解析器完成 [TASK-xyz]")
    assert ok and kind == "deliverable"


def test_phase_with_done_task_tag() -> None:
    ok, kind = validate_subject("[PHASE-2] Phase 2 完成 [DONE-TASK-g123]")
    assert ok and kind == "phase"


# ---------- 拒绝场景 ----------
def test_random_text_rejected() -> None:
    ok, _ = validate_subject("just random text")
    assert not ok


def test_task_tag_alone_rejected() -> None:
    """裸 [TASK-xxx] 没有合法主体, 应拒绝."""
    ok, _ = validate_subject("[TASK-abc]")
    assert not ok


def test_invalid_type_rejected() -> None:
    ok, _ = validate_subject("badtype: 描述")
    assert not ok


def test_missing_description_rejected() -> None:
    ok, _ = validate_subject("feat:")
    assert not ok
