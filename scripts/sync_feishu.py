#!/usr/bin/env python3
"""飞书同步脚本.

根据环境变量判断事件类型:
  - push 到 main + commit message 含 [DEL-xx]/[PHASE-x]  -> 更新多维表格 + 群消息
  - push 到 main + commit message 含 [TASK-]/[DONE-TASK-] -> 更新任务状态
  - pull_request 事件                                     -> 仅记录 PR 状态

环境变量:
  FEISHU_APP_ID, FEISHU_APP_SECRET        (必需)
  FEISHU_BITABLE_APP_TOKEN                (多维表格 token)
  FEISHU_BITABLE_TABLE_ID                 (表格 ID)
  FEISHU_WEBHOOK_URL                      (群机器人 webhook)
  EVENT_NAME, COMMIT_SHA, REPO_NAME, ACTOR
  COMMIT_MESSAGE                           (push 事件, 可能多行)
  PR_NUMBER, PR_TITLE, PR_STATE, PR_MERGED, PR_URL (PR 事件)

提交消息解析规则:
  [DEL-xx] 描述                 -> 交付物完成
  [DEL-xx][MVP|UAT|...] 描述    -> 里程碑达成 🏁
  [PHASE-x] 描述                -> 阶段完成 📦
  [TASK-xxx] / [DONE-TASK-xxx]  -> 任务状态推进 (委托 update_feishu_task)
  其他 (feat:, fix: 等)         -> 不触发同步
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any

import requests

FEISHU_BASE = "https://open.feishu.cn/open-apis"
TIMEOUT = 15

DELIVERABLE_RE = re.compile(
    r"^\[DEL-(\d+)\](?:\[([A-Z][A-Z0-9_-]*)\])?\s+(.+?)$",
    re.MULTILINE,
)
PHASE_RE = re.compile(r"^\[PHASE-(\d+)\]\s+(.+?)$", re.MULTILINE)
TASK_RE = re.compile(r"\[(DONE-)?TASK-([A-Za-z0-9_-]+)\]")


@dataclass
class ParsedMessage:
    kind: str  # "deliverable" | "milestone" | "phase" | "task"
    ident: str  # DEL-04 / PHASE-1 / TASK-xxx
    tag: str | None  # MVP / UAT / None
    description: str


def _has_task_tag(message: str) -> bool:
    """检查 commit message 是否含 [TASK-xxx] 或 [DONE-TASK-xxx]。"""
    return bool(TASK_RE.search(message))


def parse_commit(message: str) -> ParsedMessage | None:
    """解析第一行, 返回 ParsedMessage 或 None (不触发同步)。"""
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    if not first_line:
        return None

    m = DELIVERABLE_RE.match(first_line)
    if m:
        num, tag, desc = m.groups()
        kind = "milestone" if tag else "deliverable"
        return ParsedMessage(kind=kind, ident=f"DEL-{num}", tag=tag, description=desc)

    m = PHASE_RE.match(first_line)
    if m:
        num, desc = m.groups()
        return ParsedMessage(kind="phase", ident=f"PHASE-{num}", tag=None, description=desc)

    if _has_task_tag(first_line):
        return ParsedMessage(kind="task", ident="TASK", tag=None, description=first_line)

    return None


def get_tenant_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def update_bitable(
    token: str,
    app_token: str,
    table_id: str,
    parsed: ParsedMessage,
    commit_sha: str,
    actor: str,
) -> None:
    """在多维表格中新增一行记录 (简化: 仅 insert, 不去重)。"""
    url = f"{FEISHU_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    fields: dict[str, Any] = {
        "编号": parsed.ident,
        "类型": {"deliverable": "交付物", "milestone": "里程碑", "phase": "阶段"}[parsed.kind],
        "标签": parsed.tag or "",
        "描述": parsed.description,
        "Commit": commit_sha[:8],
        "提交人": actor,
        "状态": "已完成",
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": fields},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"写入多维表格失败: {data}")
    print(f"✅ 多维表格已更新: {parsed.ident} {parsed.description}")


def send_group_message(
    webhook: str, parsed: ParsedMessage, repo: str, actor: str, sha: str
) -> None:
    """向群机器人发送卡片消息。"""
    emoji_map = {"deliverable": "✅", "milestone": "🏁", "phase": "📦"}
    type_map = {"deliverable": "交付物完成", "milestone": "里程碑达成", "phase": "阶段完成"}
    color_map = {"deliverable": "green", "milestone": "orange", "phase": "blue"}

    emoji = emoji_map[parsed.kind]
    title_type = type_map[parsed.kind]
    tag_suffix = f" [{parsed.tag}]" if parsed.tag else ""

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": color_map[parsed.kind],
                "title": {
                    "tag": "plain_text",
                    "content": f"{emoji} {title_type}: {parsed.ident}{tag_suffix}",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{parsed.description}**",
                    },
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**仓库**\n{repo}"},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**提交人**\n{actor}"},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**Commit**\n{sha[:8]}"},
                        },
                    ],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看提交"},
                            "url": f"https://github.com/{repo}/commit/{sha}",
                            "type": "primary",
                        }
                    ],
                },
            ],
        },
    }
    resp = requests.post(webhook, json=card, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
        raise RuntimeError(f"群消息发送失败: {data}")
    print(f"✅ 群消息已发送: {parsed.ident}")


def handle_push() -> int:
    message = os.environ.get("COMMIT_MESSAGE", "")
    if not message:
        print("⚠️ COMMIT_MESSAGE 为空, 跳过")
        return 0

    parsed = parse_commit(message)
    if parsed is None:
        print("ℹ️ 普通提交 (未匹配 [DEL-xx] / [PHASE-x] / [TASK-xxx]), 跳过飞书同步")
        return 0

    # TASK 提交: 委托 update_feishu_task 处理状态推进
    if parsed.kind == "task":
        import update_feishu_task

        return update_feishu_task.main()

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    bitable_app = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    bitable_table = os.environ.get("FEISHU_BITABLE_TABLE_ID")
    webhook = os.environ.get("FEISHU_WEBHOOK_URL")
    sha = os.environ.get("COMMIT_SHA", "")
    repo = os.environ.get("REPO_NAME", "")
    actor = os.environ.get("ACTOR", "")

    if not (app_id and app_secret):
        print("::warning::缺少 FEISHU_APP_ID/SECRET, 跳过多维表格更新")
    else:
        try:
            token = get_tenant_token(app_id, app_secret)
            if bitable_app and bitable_table:
                update_bitable(token, bitable_app, bitable_table, parsed, sha, actor)
            else:
                print("::warning::缺少 BITABLE_APP_TOKEN/TABLE_ID, 跳过表格写入")
        except Exception as e:
            print(f"::error::多维表格更新失败: {e}", file=sys.stderr)

    if not webhook:
        print("::warning::缺少 FEISHU_WEBHOOK_URL, 跳过群消息")
    else:
        try:
            send_group_message(webhook, parsed, repo, actor, sha)
        except Exception as e:
            print(f"::error::群消息发送失败: {e}", file=sys.stderr)

    return 0


def handle_pull_request() -> int:
    """PR 事件当前仅打印日志 (可扩展为 PR 状态同步)。"""
    number = os.environ.get("PR_NUMBER", "")
    title = os.environ.get("PR_TITLE", "")
    state = os.environ.get("PR_STATE", "")
    merged = os.environ.get("PR_MERGED", "")
    url = os.environ.get("PR_URL", "")
    print(f"ℹ️ PR #{number} [{state} merged={merged}] {title}")
    print(f"    {url}")
    # 预留: 可根据需求同步 PR 状态到飞书
    return 0


def main() -> int:
    event = os.environ.get("EVENT_NAME", "")
    if event == "push":
        return handle_push()
    if event == "pull_request":
        return handle_pull_request()
    print(f"⚠️ 未知事件类型: {event}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as e:
        body = ""
        try:
            body = e.response.text  # type: ignore[union-attr]
        except Exception:
            pass
        print(f"::error::HTTP 错误: {e}\n{body}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"::error::飞书同步脚本异常: {e}", file=sys.stderr)
        raise SystemExit(1)
