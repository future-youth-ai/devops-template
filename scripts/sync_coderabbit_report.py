#!/usr/bin/env python3
"""CodeRabbit 报告 -> 飞书 Webhook 同步.

监听 GitHub 事件, 过滤出 CodeRabbit 的"有信息量"输出推送到飞书群.
按照策略 B, 只推以下两类, 忽略 walkthrough / ack / 进度提示, 避免刷屏:

  1. Summary 评论         (issue_comment, body 含 "Summary by CodeRabbit")
  2. Review 结论          (pull_request_review, state ∈ {changes_requested, approved})

安全设计:
  - 所有外部输入在进入飞书卡片前做结构/白名单校验
  - pr_title 做 lark_md 转义, 避免 markdown/mention 注入
  - body 按 UTF-8 字节数截断 (非字符数), 避免中文/emoji 超限被飞书拒收
  - pr_url 校验必须是 github.com 下的 /pull/<n> 路径

环境变量:
  FEISHU_WEBHOOK_URL        (必需, 飞书群机器人 webhook)
  EVENT_NAME                (issue_comment | pull_request_review)
  REPO_NAME                 (owner/repo)
  PR_NUMBER, PR_TITLE, PR_URL
  SENDER_LOGIN              (事件触发者, 用于双保险过滤)
  COMMENT_BODY              (issue_comment.comment.body 或 pull_request_review.review.body)
  REVIEW_STATE              (pull_request_review 事件专用)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

import config_loader

TIMEOUT = 15
CODERABBIT_BOT = "coderabbitai[bot]"

# 飞书 lark_md 元素建议 <= 4KB, 取 3000 字节保守余量
MAX_BODY_BYTES = 3000
TRUNCATE_SUFFIX = "\n\n...(已截断, 完整内容见 PR)"

# 已知事件 / review state 白名单
ALLOWED_EVENTS = {"issue_comment", "pull_request_review"}
PUSH_REVIEW_STATES = {"changes_requested", "approved"}

SUMMARY_PATTERN = re.compile(r"Summary by CodeRabbit", re.IGNORECASE)
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PR_NUMBER_PATTERN = re.compile(r"^\d+$")


# ---------- 过滤 ----------


def should_skip(event: str, sender: str, body: str, state: str) -> tuple[bool, str]:
    """返回 (是否跳过, 原因或匹配类型)."""
    if event not in ALLOWED_EVENTS:
        return True, f"未支持的事件类型: {event}"
    if sender != CODERABBIT_BOT:
        return True, f"非 CodeRabbit 事件 (sender={sender})"

    if event == "issue_comment":
        if not SUMMARY_PATTERN.search(body or ""):
            return True, "非 Summary 评论 (可能是 walkthrough/ack/进度)"
        return False, "summary"

    # pull_request_review
    if state not in PUSH_REVIEW_STATES:
        return True, f"review state={state} 不推送"
    return False, f"review-{state}"


# ---------- 校验 / 转义 ----------


def validate_pr_url(url: str) -> str:
    """只允许 https://github.com/<owner>/<repo>/pull/<n> 精确格式.

    拒绝:
        - 非 https / 非 github.com
        - /pull/<n>/files 这类子路径 (必须正好 4 段)
        - 带 query string 或 fragment
        - pull 号非纯数字

    返回规范化 URL 或空串.
    """
    if not url:
        return ""
    try:
        p = urlparse(url)
    except Exception:
        return ""
    if p.scheme != "https" or p.netloc != "github.com":
        return ""
    if p.query or p.fragment:
        return ""
    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) != 4 or parts[2] != "pull" or not parts[3].isdigit():
        return ""
    owner, repo, _, number = parts
    return f"https://github.com/{owner}/{repo}/pull/{number}"


def validate_repo(repo: str) -> str:
    """repo 必须形如 owner/repo, 否则返回空串."""
    return repo if repo and REPO_PATTERN.match(repo) else ""


def validate_pr_number(number: str) -> str:
    return number if number and PR_NUMBER_PATTERN.match(number) else ""


def escape_lark_md(text: str) -> str:
    """最小转义: 防止 pr_title 突破 markdown 链接上下文 / 触发 @ 提醒 / 注入 HTML 标签."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        # 飞书 @all/@here/@<user_id> 会触发提醒, 用全角 @ (U+FF20) 替换
        .replace("@", "＠")
        # 阻止 <b>xxx</b> 之类 HTML/lark 标签注入
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def sanitize_lark_body(text: str) -> str:
    """对非 trusted 的长文本做 lark_md 注入最小净化.

    即使 sender 已经是 coderabbitai[bot], 其 body 仍可能是转发的用户输入
    (比如 PR 作者写在 PR body 里的 @all, 再被 bot 引用). 所以对 body 也做
    一次基础净化: 替换 @ 防误提醒, 用 HTML 实体替换 <>, 防止潜在的 lark 标签注入.
    Markdown 链接/粗体等格式保留, 因为 CodeRabbit 的输出靠它渲染可读性.
    """
    if not text:
        return ""
    return text.replace("@", "＠").replace("<", "&lt;").replace(">", "&gt;")


def truncate_bytes(body: str, limit: int = MAX_BODY_BYTES) -> str:
    """按 UTF-8 字节数截断, 保证不切断多字节字符."""
    if not body:
        return "(无内容)"
    encoded = body.encode("utf-8")
    if len(encoded) <= limit:
        return body
    # 预留 suffix 的字节
    suffix_bytes = TRUNCATE_SUFFIX.encode("utf-8")
    budget = max(limit - len(suffix_bytes), 0)
    truncated = encoded[:budget]
    # 回退直到能解码 (避免切在多字节字符中间)
    for _ in range(4):  # UTF-8 字符最长 4 字节
        try:
            return truncated.decode("utf-8") + TRUNCATE_SUFFIX
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return "(内容截断失败)"


# ---------- 卡片 ----------


def build_card(
    kind: str,
    repo: str,
    pr_number: str,
    pr_title: str,
    pr_url: str,
    body: str,
) -> dict:
    """构造飞书交互式卡片 (所有外部输入已校验/转义)."""
    title_map = {
        "summary": ("📝", "CodeRabbit 审查摘要", "blue"),
        "review-approved": ("✅", "CodeRabbit 审查通过", "green"),
        "review-changes_requested": ("❌", "CodeRabbit 要求修改", "red"),
    }
    emoji, title, color = title_map.get(kind, ("🐰", f"CodeRabbit [{kind}]", "grey"))

    safe_title = escape_lark_md(pr_title) or "(无标题)"
    # 链接文本中如果 pr_url 校验失败, 降级为纯文本标题
    link_md = f"[{safe_title}]({pr_url})" if pr_url else safe_title
    header_suffix = f"{repo}#{pr_number}" if repo and pr_number else "PR"

    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**PR**: {link_md}"}},
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": truncate_bytes(sanitize_lark_body(body)),
            },
        },
    ]
    if pr_url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看 PR"},
                        "url": pr_url,
                        "type": "primary",
                    }
                ],
            }
        )

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": color,
                "title": {
                    "tag": "plain_text",
                    "content": f"{emoji} {title} · {header_suffix}",
                },
            },
            "elements": elements,
        },
    }


# ---------- 主流程 ----------


def main() -> int:
    event = os.environ.get("EVENT_NAME", "")
    sender = os.environ.get("SENDER_LOGIN", "")
    body = os.environ.get("COMMENT_BODY", "") or ""
    state = os.environ.get("REVIEW_STATE", "")

    skip, reason = should_skip(event, sender, body, state)
    if skip:
        print(f"⏭️  跳过: {reason}")
        return 0

    webhook = config_loader.get("feishu", "webhook_url", env="FEISHU_WEBHOOK_URL")
    if not webhook:
        print("::warning::缺少 FEISHU_WEBHOOK_URL, 跳过推送")
        return 0

    # 所有外部输入 -> 校验白名单 / 转义
    repo = validate_repo(os.environ.get("REPO_NAME", ""))
    pr_number = validate_pr_number(os.environ.get("PR_NUMBER", ""))
    pr_url = validate_pr_url(os.environ.get("PR_URL", ""))
    pr_title = os.environ.get("PR_TITLE", "") or ""

    card = build_card(reason, repo, pr_number, pr_title, pr_url, body)

    # 如果配了 FEISHU_WEBHOOK_SECRET, 开启签名校验模式 (飞书自定义机器人的 "签名校验")
    # 否则走 "IP 白名单 / 关键词" 模式, 不带签名字段
    webhook_secret = config_loader.get("feishu", "webhook_secret", env="FEISHU_WEBHOOK_SECRET")
    payload: dict = dict(card)
    if webhook_secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _sign(timestamp, webhook_secret)

    resp = requests.post(webhook, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # 飞书群 webhook: 成功时 code 与 StatusCode 都应为 0 (一般只返回其中之一);
    # 任一字段非零都视为失败, 用 OR 而非 AND 避免单字段错误被吞
    if data.get("code", 0) != 0 or data.get("StatusCode", 0) != 0:
        raise RuntimeError(f"飞书群消息发送失败: {data}")
    print(f"✅ 已推送到飞书: kind={reason}, PR #{pr_number or '?'}")
    return 0


def _sign(timestamp: str, secret: str) -> str:
    """飞书自定义机器人签名: HMAC-SHA256(secret, f'{timestamp}\\n{secret}') 再 base64.

    参考: https://open.feishu.cn/document/client-docs/bot-v1/add-custom-bot
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as e:
        err_body = ""
        try:
            err_body = e.response.text  # type: ignore[union-attr]
        except Exception:
            pass
        print(f"::error::HTTP 错误: {e}\n{err_body}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"::error::CodeRabbit 同步脚本异常: {e}", file=sys.stderr)
        raise SystemExit(1)
