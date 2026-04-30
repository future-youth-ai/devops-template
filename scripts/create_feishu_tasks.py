"""读 ACTION_ITEMS_JSON, 在飞书多维表格(需求池)创建记录, 维护 .planning/tasks.json 映射.

环境变量:
  FEISHU_APP_ID / FEISHU_APP_SECRET   必需
  ACTION_ITEMS_JSON                    必需 (extract step 的 JSON 数组字符串)
  ISSUE_NUMBER                         必需 (用于 tasks.json 索引 key)
  MEETING_DATE                         可选 (YYYY-MM-DD, 用于填 提出日期)
  REPO_NAME                            可选 (owner/repo, 用于拼 GitHub issue 链接)
  GITHUB_OUTPUT                        可选 (写 record_ids / task_md 给下游 step)
  FEISHU_BITABLE_APP_TOKEN             必需
  FEISHU_BITABLE_TABLE_ID              必需

行为:
  - 对每个 item 调 bitable record create API 写入需求池
  - 字段映射: title→需求描述, due_date→预计交付日期, 进展状态→未启动
  - 把 {issue#N: [{record_id, title, assignee_name, due_date}]} 写到 .planning/tasks.json
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import requests
from pydantic import BaseModel, Field, ValidationError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from feishu_content import FEISHU_BASE, get_tenant_token

# 锚定仓库根目录, 不依赖 cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_JSON_PATH = _REPO_ROOT / ".planning" / "tasks.json"


def _build_session() -> requests.Session:
    """带重试的 requests session: 飞书 5xx / 429 / 502 / 503 / 504 自动重试."""
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET", "PATCH"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


_SESSION = _build_session()


class ActionItemInput(BaseModel):
    """对 ACTION_ITEMS_JSON 的 schema 校验, 防上游格式异常."""

    title: str = Field(default="未命名", min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    assignee_name: str = ""
    due_date: str | None = None
    priority: str = Field(default="P2", pattern=r"^P[0-3]$")


def create_bitable_record(
    tenant_token: str,
    app_token: str,
    table_id: str,
    title: str,
    description: str,
    due_date: str | None,
    assignee_name: str,
    priority: str = "P2",
    meeting_date: str = "",
    issue_url: str = "",
) -> str:
    """在多维表格创建一条记录, 返回 record_id."""
    fields: dict = {
        "需求描述": title,
        "进展状态": "未启动",
        "优先级": priority,
    }
    if description:
        fields["备注"] = description
    if assignee_name:
        fields["备注"] = (
            f"[负责人: {assignee_name}] {description}"
            if description
            else f"[负责人: {assignee_name}]"
        )
    if due_date:
        try:
            dt = datetime.fromisoformat(due_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            fields["预计交付日期"] = int(dt.timestamp()) * 1000
        except ValueError:
            pass
    if meeting_date:
        try:
            dt = datetime.fromisoformat(meeting_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            fields["提出日期"] = int(dt.timestamp()) * 1000
        except ValueError:
            pass
    if issue_url:
        fields["相关文档"] = issue_url

    r = _SESSION.post(
        f"{FEISHU_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        headers={"Authorization": f"Bearer {tenant_token}"},
        json={"fields": fields},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"create record HTTP {r.status_code}: {r.text}")
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"create record 失败: {data}")
    return data.get("data", {}).get("record", {}).get("record_id", "")


def load_tasks_map() -> dict:
    """读 .planning/tasks.json, 不存在或脏数据则返回空 dict."""
    if not TASKS_JSON_PATH.exists():
        return {}
    try:
        data = json.loads(TASKS_JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"::warning::tasks.json 解析失败, 视作空 mapping: {e}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"::warning::tasks.json 顶层不是 dict (got {type(data).__name__}), 视作空",
            file=sys.stderr,
        )
        return {}
    cleaned: dict = {}
    for k, v in data.items():
        if isinstance(v, list):
            cleaned[k] = [it for it in v if isinstance(it, dict)]
    return cleaned


def save_tasks_map(mapping: dict) -> None:
    """落盘 .planning/tasks.json (sorted, indent=2 便于 diff)."""
    TASKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_JSON_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    items_raw = os.environ.get("ACTION_ITEMS_JSON", "[]")
    try:
        raw_items = json.loads(items_raw)
    except json.JSONDecodeError as e:
        print(f"::error::ACTION_ITEMS_JSON 解析失败: {e}", file=sys.stderr)
        return 2
    if not isinstance(raw_items, list) or not raw_items:
        print("ℹ️ 没有 action items, 跳过任务创建")
        return 0

    items: list[dict] = []
    for ri in raw_items:
        if not isinstance(ri, dict):
            continue
        try:
            items.append(ActionItemInput(**ri).model_dump())
        except ValidationError as e:
            print(f"::warning::跳过格式不对的 item: {ri} ({e})", file=sys.stderr)
    if not items:
        print("ℹ️ 没有合法 action items, 跳过任务创建")
        return 0

    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    issue_num = os.environ.get("ISSUE_NUMBER", "")
    if not (app_id and app_secret and issue_num):
        print(
            "::error::缺 FEISHU_APP_ID / FEISHU_APP_SECRET / ISSUE_NUMBER",
            file=sys.stderr,
        )
        return 2

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
    if not (app_token and table_id):
        print(
            "::error::缺 FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID",
            file=sys.stderr,
        )
        return 2
    tenant_token = get_tenant_token(app_id, app_secret)

    meeting_date = os.environ.get("MEETING_DATE", "")
    repo_name = os.environ.get("REPO_NAME", "")
    issue_url = f"https://github.com/{repo_name}/issues/{issue_num}" if repo_name else ""

    # 幂等: 检查已创建的记录, 按 title 跨 issue 去重
    mapping = load_tasks_map()
    key = f"issue#{issue_num}"
    existing_titles = {e.get("title") for entries in mapping.values() for e in entries}

    created: list[dict] = []
    for item in items:
        if item.get("title") in existing_titles:
            print(f"  ⏭️ 跳过已存在: {item.get('title')}")
            continue
        try:
            record_id = create_bitable_record(
                tenant_token,
                app_token=app_token,
                table_id=table_id,
                title=item.get("title", "未命名"),
                description=item.get("description", ""),
                due_date=item.get("due_date"),
                assignee_name=item.get("assignee_name", ""),
                priority=item.get("priority", "P2"),
                meeting_date=meeting_date,
                issue_url=issue_url,
            )
        except Exception as e:
            print(f"::warning::创建记录 {item.get('title')!r} 失败: {e}", file=sys.stderr)
            continue
        if record_id:
            created.append(
                {
                    "record_id": record_id,
                    "title": item.get("title", ""),
                    "assignee_name": item.get("assignee_name", ""),
                    "due_date": item.get("due_date"),
                }
            )
            print(f"  ✅ {item.get('title')} -> {record_id}")

    # 维护 tasks.json
    mapping.setdefault(key, []).extend(created)
    save_tasks_map(mapping)
    print(f"已写 {TASKS_JSON_PATH}, key={key}, 新增 {len(created)} 条")

    # 输出给 workflow 下游 step
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        record_ids = " ".join(c["record_id"] for c in created)
        md_lines = (
            "\n".join(
                f"- **{c['title']}** ({c['assignee_name'] or '未指派'}, "
                f"{c['due_date'] or '无截止'}): `{c['record_id']}`"
                for c in created
            )
            or "_(无)_"
        )
        delim = f"TASK_MD_{uuid.uuid4().hex}"
        with open(gh_out, "a") as f:
            f.write(f"task_count={len(created)}\n")
            f.write(f"record_ids={record_ids}\n")
            f.write(f"task_md<<{delim}\n{md_lines}\n{delim}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
