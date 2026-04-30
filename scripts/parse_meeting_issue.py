"""从 GitHub Issue Form 生成的 body 解析字段, 写到 GITHUB_OUTPUT.

Issue Form 提交后, GitHub 会把表单字段拼成 markdown body, 形如:

  ### 会议标题

  4月23日 项目立项会

  ### 会议日期 (YYYY-MM-DD)

  2026-04-23

  ### 飞书链接 (妙记/Docx/Wiki)

  https://meetings.feishu.cn/minutes/xxx

  ### 备注 (可选)

  _No response_

我们按 `### <Label>` 锚点提取每段内容.
"""

from __future__ import annotations

import os
import re
import sys


def extract_field(body: str, label: str) -> str:
    """提取 issue body 中 `### <label>` 段的内容."""
    pattern = rf"###\s*{re.escape(label)}\s*\n+(.*?)(?=\n###|\Z)"
    m = re.search(pattern, body, re.S)
    if not m:
        return ""
    val = m.group(1).strip()
    # GitHub 对未填的可选字段会写 "_No response_"
    if val == "_No response_":
        return ""
    return val


def main() -> int:
    body = os.environ.get("ISSUE_BODY", "") or ""
    fallback_title = os.environ.get("ISSUE_TITLE", "未命名").replace("[Meeting]", "").strip()

    title = extract_field(body, "会议标题") or fallback_title
    date = extract_field(body, "会议日期 (YYYY-MM-DD)")
    url = extract_field(body, "飞书链接 (妙记/Docx/Wiki)")

    if not url:
        print("::error::issue body 里没找到飞书链接字段", file=sys.stderr)
        return 2

    gh_out = os.environ.get("GITHUB_OUTPUT", "")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"meeting_title={title}\n")
            f.write(f"meeting_date={date}\n")
            f.write(f"feishu_url={url}\n")

    print(
        f"meeting_title={title}\nmeeting_date={date}\nfeishu_url={url}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
