"""把会议元信息 + 提取结果归档为 markdown 到 .planning/meetings/.

策略 B (链接归档): 不存原文 transcript, 只存元信息 + action items + 任务 GUIDs.
原始 transcript 留在飞书云端, 通过 issue 里的 link 点过去.

环境变量:
  MEETING_TITLE      可选, 默认 "未命名会议"
  MEETING_DATE       可选, 默认今天 UTC
  ISSUE_NUMBER       必需 (用于反查 .planning/tasks.json)
  FEISHU_URL         可选, 写在归档里方便溯源

输出:
  - 写文件 .planning/meetings/{date}-issue{n}.md
  - 把文件路径打到 stdout (workflow 用 $(python ...) 拿)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# 路径安全: ISSUE_NUMBER 必须纯数字, MEETING_DATE 必须 YYYY-MM-DD
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISSUE_NUM_RE = re.compile(r"^\d+$")

# 锚定仓库根目录, 不依赖 cwd. 以模块顶层常量方式暴露便于测试 monkeypatch.
_REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_JSON_PATH = _REPO_ROOT / ".planning" / "tasks.json"
MEETINGS_DIR = _REPO_ROOT / ".planning" / "meetings"

TEMPLATE = """# {title}

- **日期**: {date}
- **入口 issue**: #{issue_number}
- **原始链接**: {feishu_url}
- **生成时间 (UTC)**: {generated_at}

## AI 提取的 Action Items

{table}

> 归档策略 B: transcript 原文留在飞书, 此处仅留元信息和 AI 抽取结果.
"""


def _md_escape(s: str) -> str:
    """转义 markdown 表格单元格里的危险字符:
    - `|` 会破坏表格列分隔
    - 换行会破坏表格行
    - `` ` `` 会开 inline code
    - `*` / `_` 会触发斜体/粗体
    - `<` / `>` 可能触发 HTML 解析
    """
    return (
        s.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_table(items: list[dict]) -> str:
    """把 tasks.json 里某 issue 下的条目渲染成 markdown 表格."""
    if not items:
        return "_(本次会议未提取到 action items)_"
    lines = [
        "| # | 任务 | 负责人 | 截止 | 飞书 Record ID |",
        "|---|---|---|---|---|",
    ]
    for i, it in enumerate(items, 1):
        title = _md_escape(it.get("title") or "")
        assignee = _md_escape(it.get("assignee_name") or "未指派")
        due = it.get("due_date") or "—"
        record_id = it.get("record_id") or "(创建失败)"
        lines.append(f"| {i} | {title} | {assignee} | {due} | `{record_id}` |")
    return "\n".join(lines)


def main() -> int:
    title = os.environ.get("MEETING_TITLE", "").strip() or "未命名会议"
    date = os.environ.get("MEETING_DATE", "").strip()
    if not date:
        date = datetime.now(UTC).strftime("%Y-%m-%d")

    # 路径安全校验: 阻断 ../ 等穿越
    if not DATE_RE.fullmatch(date):
        print(
            f"::error::MEETING_DATE 格式必须是 YYYY-MM-DD (got {date!r})",
            file=sys.stderr,
        )
        return 2

    issue_num = os.environ.get("ISSUE_NUMBER", "").strip()
    if not ISSUE_NUM_RE.fullmatch(issue_num):
        print(
            f"::error::ISSUE_NUMBER 必须为纯数字 (got {issue_num!r})",
            file=sys.stderr,
        )
        return 2

    feishu_url = os.environ.get("FEISHU_URL", "").strip() or "(未提供)"

    # 从 tasks.json 取本次的 created 条目, 做类型兜底
    tasks_path = TASKS_JSON_PATH
    items: list[dict] = []
    if tasks_path.exists():
        try:
            mapping = json.loads(tasks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("::warning::tasks.json 解析失败, 归档表格留空", file=sys.stderr)
            mapping = {}
        if isinstance(mapping, dict):
            raw_items = mapping.get(f"issue#{issue_num}", [])
            if isinstance(raw_items, list):
                # 只保留 dict 项, 防脏数据让 build_table 崩
                items = [it for it in raw_items if isinstance(it, dict)]

    md = TEMPLATE.format(
        title=title,
        date=date,
        issue_number=issue_num,
        feishu_url=feishu_url,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        table=build_table(items),
    )

    out_path = MEETINGS_DIR / f"{date}-issue{issue_num}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    # 输出仓库根的相对路径供 workflow 用
    try:
        rel_path = out_path.relative_to(_REPO_ROOT)
        print(str(rel_path))
    except ValueError:
        # 测试场景下 MEETINGS_DIR 被 patch 到 _REPO_ROOT 之外, 直接输出绝对路径
        print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
