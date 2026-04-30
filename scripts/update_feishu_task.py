"""解析 commit 里的 [TASK-xxx] / [DONE-TASK-xxx], 更新飞书多维表格记录状态.

环境变量:
  FEISHU_APP_ID / FEISHU_APP_SECRET    必需 (或 config.yml)
  COMMIT_MESSAGE                        必需 (从 sync_feishu workflow 传)
  FEISHU_BITABLE_APP_TOKEN             必需 (或 config.yml)
  FEISHU_BITABLE_TABLE_ID              必需 (或 config.yml)

行为:
  - 解析 commit subject 里的 [TASK-xxx] / [DONE-TASK-xxx]
  - xxx 即为飞书多维表格 record_id (如 recXXXXX), 直接使用
  - DONE 标签   -> 更新进展状态为 "验收完成"
  - 普通 TASK 标签 -> 更新进展状态为 "开发中"
"""

from __future__ import annotations

import os
import re
import sys

import requests

import config_loader
from feishu_content import FEISHU_BASE, get_tenant_token

TASK_RE = re.compile(r"\[(DONE-)?TASK-([A-Za-z0-9_-]+)\]")


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

    app_id = config_loader.get("feishu", "app_id", env="FEISHU_APP_ID")
    app_secret = config_loader.get("feishu", "app_secret", env="FEISHU_APP_SECRET")
    if not (app_id and app_secret):
        print("::warning::缺 FEISHU_APP_ID/SECRET, 跳过", file=sys.stderr)
        return 0

    app_token = config_loader.get("feishu", "bitable_app_token", env="FEISHU_BITABLE_APP_TOKEN")
    table_id = config_loader.get("feishu", "bitable_table_id", env="FEISHU_BITABLE_TABLE_ID")
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
        record_id = m.group(2)
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
