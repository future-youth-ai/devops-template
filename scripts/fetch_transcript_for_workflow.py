"""调 feishu_url 解析 + feishu_content 拉文本, 写到 GITHUB_OUTPUT.

环境变量:
  FEISHU_URL              必需, issue 里的链接
  FEISHU_APP_ID           必需
  FEISHU_APP_SECRET       必需
  GITHUB_OUTPUT           workflow 自动设置

输出:
  transcript<<EOF\n<text>\nEOF  到 GITHUB_OUTPUT
"""

from __future__ import annotations

import os
import sys

from feishu_content import fetch_content, get_tenant_token
from feishu_url import InvalidFeishuURL, parse_feishu_url


def main() -> int:
    url = os.environ.get("FEISHU_URL", "")
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not (app_id and app_secret):
        print("::error::FEISHU_APP_ID / FEISHU_APP_SECRET 未设置", file=sys.stderr)
        return 2

    try:
        kind, token = parse_feishu_url(url)
    except InvalidFeishuURL as e:
        print(f"::error::飞书 URL 无效: {e}", file=sys.stderr)
        return 2

    print(f"📥 拉取 kind={kind}, token={token[:8]}...")
    try:
        tenant_token = get_tenant_token(app_id, app_secret)
        text = fetch_content(kind, token, tenant_token)
    except Exception as e:
        print(f"::error::拉取飞书内容失败: {e}", file=sys.stderr)
        return 2

    print(f"✅ 拿到 {len(text)} 字符")

    gh_out = os.environ.get("GITHUB_OUTPUT", "")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"transcript<<TRANSCRIPT_EOF\n{text}\nTRANSCRIPT_EOF\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
