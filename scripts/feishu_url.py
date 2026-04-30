"""飞书资源 URL 解析: URL → (kind, token).

支持的 URL 形态:
  https://meetings.feishu.cn/minutes/<token>          -> ("minutes", token)
  https://*.feishu.cn/docx/<doc_id>                   -> ("docx", doc_id)
  https://*.feishu.cn/docs/<doc_id>                   -> ("docs", doc_id)
  https://*.feishu.cn/wiki/<wiki_token>               -> ("wiki", wiki_token)
  https://*.larksuite.com/<kind>/<token>              -> 同上 (国际版)

不支持的安全约束:
  - 必须 https
  - 域名必须 *.feishu.cn 或 *.larksuite.com (含 meetings.feishu.cn 子域名)
  - kind 必须在白名单
  - token 长度 >= 8 (避免误识别短路径段)
"""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_KINDS = {"minutes", "docx", "docs", "wiki"}


class InvalidFeishuURL(ValueError):
    """非法的飞书 URL."""


def parse_feishu_url(url: str) -> tuple[str, str]:
    """返回 (kind, token). 不合法抛 InvalidFeishuURL."""
    if not url or not isinstance(url, str):
        raise InvalidFeishuURL("URL 为空")

    p = urlparse(url.strip())
    if p.scheme not in {"https"}:
        raise InvalidFeishuURL(f"协议必须为 https: {url}")

    netloc = p.netloc.lower()
    if not (
        netloc.endswith(".feishu.cn")
        or netloc.endswith(".larksuite.com")
        or netloc == "feishu.cn"
        or netloc == "larksuite.com"
    ):
        raise InvalidFeishuURL(f"非飞书域名: {netloc}")

    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) < 2:
        raise InvalidFeishuURL(f"路径段不足 (需要至少 /<kind>/<token>): {p.path}")

    kind, token = parts[0], parts[1]
    if kind not in ALLOWED_KINDS:
        raise InvalidFeishuURL(f"未支持的资源类型 {kind!r}, 仅支持 {sorted(ALLOWED_KINDS)}")
    if not token or len(token) < 8:
        raise InvalidFeishuURL(f"token 长度异常 (需 >=8): {token}")
    return kind, token
