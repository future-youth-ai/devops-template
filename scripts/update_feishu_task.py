"""解析 commit 里的 [TASK-xxx] / [DONE-TASK-xxx], 更新飞书多维表格记录状态.

环境变量:
  FEISHU_APP_ID / FEISHU_APP_SECRET    必需
  COMMIT_MESSAGE                        必需 (从 sync_feishu workflow 传)
  FEISHU_BITABLE_APP_TOKEN             必需
  FEISHU_BITABLE_TABLE_ID              必需

行为:
  - 解析 commit subject 里的 [TASK-xxx] / [DONE-TASK-xxx]
  - 反查 .planning/tasks.json 拿真实 record_id (支持前缀匹配)
  - DONE 标签   -> 更新进展状态为 "验收完成"
  - 普通 TASK 标签 -> 更新进展状态为 "开发中"
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

from feishu_content import FEISHU_BASE, get_tenant_token

TASK_RE = re.compile(r"\[(DONE-)?TASK-([A-Za-z0-9_-]+)\]")
_REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_JSON = _REPO_ROOT / ".planning" / "tasks.json"


def find_record_id(commit_id: str) -> str | None:
    """从 tasks.json 找匹配的真实 record_id.

    匹配规则:
      1) 精确匹配优先
      2) 唯一前缀匹配
      3) 多个前缀命中 -> 视为歧义, 返回 None 并 warn
    """
    if not TASKS_JSON.exists():
        return None
    try:
        mapping = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    exact: str | None = None
    prefix_matches: list[str] = []
    for entries in mapping.values():
        if not isinstance(entries, list):
            continue
        for e in entries:
            rid = e.get("record_id", "")
            if not rid:
                continue
            if rid == commit_id:
                exact = rid
                break
            if rid.startswith(commit_id):
                prefix_matches.append(rid)
        if exact:
            break
    if exact:
        return exact
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if prefix_matches:
        print(
            f"::warning::TASK-{commit_id} 前缀匹配到多个记录: {prefix_matches}, 跳过",
            file=sys.stderr,
        )
    return None


def update_record_status(
    tenant_token: str,
    app_token: str,
    table_id: str,
    record_id: str,
    status: str,
) -> None:
    """更新多维表格记录的进展状态."""
    r = requests.put(
        f"{FEISHU_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        headers={"Authorization": f"Bearer {tenant_token}"},
        json={"fields": {"进展状态": status}},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"update record HTTP {r.status_code}: {r.text}")
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"update record 失败: {data}")
    print(f"  ✅ record {record_id} -> {status}")


def main() -> int:
    msg = os.environ.get("COMMIT_MESSAGE", "")
    if not msg:
        print("ℹ️ COMMIT_MESSAGE 为空, 跳过")
        return 0

    matches = list(TASK_RE.finditer(msg))
    if not matches:
        print("ℹ️ commit 不含 [TASK-xxx] / [DONE-TASK-xxx], 跳过")
        return 0

    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not (app_id and app_secret):
        print("::warning::缺 FEISHU_APP_ID/SECRET, 跳过", file=sys.stderr)
        return 0

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
    if not (app_token and table_id):
        print("::warning::缺 FEISHU_BITABLE_APP_TOKEN/TABLE_ID, 跳过", file=sys.stderr)
        return 0

    try:
        tenant_token = get_tenant_token(app_id, app_secret)
    except Exception as e:
        print(f"::error::获取 token 失败: {e}", file=sys.stderr)
        return 1

    failures = 0
    for m in matches:
        is_done = bool(m.group(1))
        commit_id = m.group(2)
        record_id = find_record_id(commit_id)
        if not record_id:
            print(
                f"::warning::未在 .planning/tasks.json 找到 TASK-{commit_id}",
                file=sys.stderr,
            )
            failures += 1
            continue
        status = "验收完成" if is_done else "开发中"
        try:
            update_record_status(tenant_token, app_token, table_id, record_id, status)
        except Exception as e:
            print(
                f"::warning::更新记录 {record_id} 失败: {e}",
                file=sys.stderr,
            )
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
