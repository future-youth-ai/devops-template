#!/usr/bin/env python3
"""Commit message linter.

校验 PR 中所有 commit 消息是否符合规范:
  1. [DEL-xx] 描述                     -> 交付物
  2. [DEL-xx][MVP|UAT|...] 描述        -> 里程碑交付
  3. [PHASE-x] 描述                    -> 阶段交付
  4. type: 描述                        -> 普通提交
     type ∈ {feat, fix, docs, style, refactor, perf, test, chore, build, ci, revert}

用法:
    python scripts/commit_lint.py <BASE_SHA> <HEAD_SHA>

所有 commit 必须通过校验，否则以非零状态退出并打印违规信息。
"""

from __future__ import annotations

import re
import subprocess
import sys

import config_loader

# 交付物: [DEL-01] 或 [DEL-01][MVP] 或 [DEL-01][UAT] 等
DELIVERABLE_PATTERN = re.compile(r"^\[DEL-\d+\](?:\[[A-Z][A-Z0-9_-]*\])?\s+\S.*$")

# 阶段: [PHASE-1] 描述
PHASE_PATTERN = re.compile(r"^\[PHASE-\d+\]\s+\S.*$")

# Conventional commits: feat: xxx / fix(scope): xxx
CONVENTIONAL_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "chore",
    "build",
    "ci",
    "revert",
)


def _build_conventional_pattern(types: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(rf"^(?:{'|'.join(types)})(?:\([\w\-./]+\))?!?:\s+\S.*$")


CONVENTIONAL_PATTERN = _build_conventional_pattern(CONVENTIONAL_TYPES)

# 允许的 merge / revert 自动提交（由 GitHub 生成）
MERGE_PATTERN = re.compile(r"^Merge (branch|pull request|remote-tracking)")

# 可选的尾标签: [TASK-<id>] / [DONE-TASK-<id>]
# - 普通 TASK 标签:  推进任务 (in progress)
# - DONE-TASK 标签:  完成任务 (调用 PATCH 标记 completed)
# 这两种都允许出现在前述四类主体之后, 由 sync_feishu / update_feishu_task 解析.
TASK_TAG_RE = re.compile(r"\s*\[(?:DONE-)?TASK-[A-Za-z0-9_-]+\]\s*$")


def get_commits(base: str, head: str) -> list[tuple[str, str]]:
    """返回 [(sha, subject)] 列表 (base, head] 区间。"""
    rng = f"{base}..{head}" if base else head
    result = subprocess.run(
        ["git", "log", "--format=%H%x1f%s", rng],
        capture_output=True,
        text=True,
        check=True,
    )
    commits: list[tuple[str, str]] = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x1f")
        commits.append((sha, subject))
    return commits


def validate_subject(subject: str) -> tuple[bool, str]:
    """返回 (是否合法, 错误信息或匹配到的类型)。

    允许在前述格式后追加可选 [TASK-xxx] 或 [DONE-TASK-xxx] 尾标签,
    例如 'feat(api): 实现登录 [TASK-abc123]' 或 'fix: 修 bug [DONE-TASK-xyz]'.
    校验时先把尾标签剥掉, 再判主体格式.
    """
    # 剥掉尾部任务标签 (如有), 只校验主体
    bare = TASK_TAG_RE.sub("", subject).strip()

    if MERGE_PATTERN.match(bare):
        return True, "merge"
    if DELIVERABLE_PATTERN.match(bare):
        return True, "deliverable"
    if PHASE_PATTERN.match(bare):
        return True, "phase"
    if CONVENTIONAL_PATTERN.match(bare):
        return True, "conventional"
    return False, (
        "必须匹配以下格式之一:\n"
        "    [DEL-xx] 描述                       (交付物)\n"
        "    [DEL-xx][MVP] 描述                  (里程碑)\n"
        "    [PHASE-x] 描述                      (阶段)\n"
        f"    <type>: 描述   (type ∈ {', '.join(CONVENTIONAL_TYPES)})\n"
        "  以上格式后可选追加 [TASK-xxx] 或 [DONE-TASK-xxx] 尾标签"
    )


def main(argv: list[str]) -> int:
    global CONVENTIONAL_PATTERN
    if len(argv) < 3:
        print("用法: commit_lint.py <BASE_SHA> <HEAD_SHA>", file=sys.stderr)
        return 2

    # 从 config.yml 加载额外的 commit types
    cfg = config_loader.load_config()
    extra = cfg.get("commit", {}).get("extra_types", [])
    if extra:
        all_types = CONVENTIONAL_TYPES + tuple(extra)
        CONVENTIONAL_PATTERN = _build_conventional_pattern(all_types)

    base, head = argv[1], argv[2]
    try:
        commits = get_commits(base, head)
    except subprocess.CalledProcessError as e:
        print(f"::error::git log 失败: {e.stderr}", file=sys.stderr)
        return 2

    if not commits:
        print("⚠️  没有找到任何 commit, 跳过校验")
        return 0

    failures: list[tuple[str, str, str]] = []
    for sha, subject in commits:
        ok, info = validate_subject(subject)
        short_sha = sha[:8]
        if ok:
            print(f"  ✅ {short_sha} [{info}] {subject}")
        else:
            print(f"  ❌ {short_sha} {subject}")
            failures.append((short_sha, subject, info))

    if failures:
        print("\n以下 commit 消息不符合规范:\n", file=sys.stderr)
        for short_sha, subject, reason in failures:
            print(f"::error::{short_sha} {subject}", file=sys.stderr)
            for line in reason.splitlines():
                print(f"    {line}", file=sys.stderr)
            print(file=sys.stderr)
        return 1

    print(f"\n✅ 共校验 {len(commits)} 个 commit, 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
