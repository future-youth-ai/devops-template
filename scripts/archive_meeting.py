"""归档会议记录到飞书云文档.

环境变量:
  MEETING_TITLE          会议标题
  MEETING_DATE           会议日期 (YYYY-MM-DD)
  ISSUE_NUMBER           GitHub issue 编号
  FEISHU_URL             飞书原始链接 (可选)
  ACTION_ITEMS_JSON      行动项 JSON (可选, 从 extract step 传)
  FEISHU_APP_ID/SECRET   飞书凭证 (env 或 config.yml)
  GITHUB_OUTPUT          输出文档 URL 给下游 step

行为:
  - 从 config.yml 读 feishu.doc_template_token
  - 调飞书 Drive API 从模板复制文档
  - 返回文档 URL
"""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime

import requests

import config_loader
from feishu_content import FEISHU_BASE, get_tenant_token

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISSUE_NUM_RE = re.compile(r"^\d+$")
TIMEOUT = 30


def copy_doc_from_template(token: str, template_token: str, title: str) -> str:
    """从模板复制文档, 返回新文档 token."""
    r = requests.post(
        f"{FEISHU_BASE}/drive/v1/files/copy",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "type": "docx",
            "token": template_token,
            "name": title,
        },
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"copy doc HTTP {r.status_code}: {r.text}")
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"copy doc 失败: {data}")
    return data.get("data", {}).get("file", {}).get("token", "")


def main() -> int:
    title = os.environ.get("MEETING_TITLE", "").strip() or "未命名会议"
    date = os.environ.get("MEETING_DATE", "").strip()
    if not date:
        date = datetime.now(UTC).strftime("%Y-%m-%d")
    issue_num = os.environ.get("ISSUE_NUMBER", "").strip()

    if not DATE_RE.fullmatch(date):
        print(f"::error::MEETING_DATE 格式必须是 YYYY-MM-DD (got {date!r})", file=sys.stderr)
        return 2
    if not issue_num or not ISSUE_NUM_RE.fullmatch(issue_num):
        print(f"::error::ISSUE_NUMBER 必须是纯数字 (got {issue_num!r})", file=sys.stderr)
        return 2

    template_token = config_loader.get(
        "feishu", "doc_template_token", env="FEISHU_DOC_TEMPLATE_TOKEN"
    )
    if not template_token:
        print("::error::缺少 feishu.doc_template_token 配置", file=sys.stderr)
        return 2

    app_id = config_loader.get("feishu", "app_id", env="FEISHU_APP_ID")
    app_secret = config_loader.get("feishu", "app_secret", env="FEISHU_APP_SECRET")
    if not (app_id and app_secret):
        print("::error::缺少 FEISHU_APP_ID / FEISHU_APP_SECRET", file=sys.stderr)
        return 2

    try:
        token = get_tenant_token(app_id, app_secret)
        doc_title = f"{date} {title} (issue #{issue_num})"
        doc_token = copy_doc_from_template(token, template_token, doc_title)
    except Exception as e:
        print(f"::error::创建飞书文档失败: {e}", file=sys.stderr)
        return 1

    doc_url = f"https://docs.feishu.cn/docx/{doc_token}"
    print(f"✅ 会议归档文档已创建: {doc_url}")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"archive_url={doc_url}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
