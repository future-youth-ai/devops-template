"""feishu_url 单测."""

from __future__ import annotations

import pytest

from feishu_url import InvalidFeishuURL, parse_feishu_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://meetings.feishu.cn/minutes/abc12345xyz",
            ("minutes", "abc12345xyz"),
        ),
        (
            "https://example.feishu.cn/docx/doxcnXXXXXXXXX",
            ("docx", "doxcnXXXXXXXXX"),
        ),
        (
            "https://example.feishu.cn/docs/doccnXXXXXXXXX",
            ("docs", "doccnXXXXXXXXX"),
        ),
        (
            "https://example.feishu.cn/wiki/wikcnXXXXXXXXXXXX",
            ("wiki", "wikcnXXXXXXXXXXXX"),
        ),
        (
            "https://example.larksuite.com/docx/doxxxxxxxxx",
            ("docx", "doxxxxxxxxx"),
        ),
        (
            "https://meetings.feishu.cn/minutes/abc12345xyz?from=email",
            ("minutes", "abc12345xyz"),  # query string 不影响
        ),
        (
            "  https://meetings.feishu.cn/minutes/abc12345xyz  ",  # 前后空白
            ("minutes", "abc12345xyz"),
        ),
    ],
)
def test_valid_urls(url: str, expected: tuple[str, str]) -> None:
    assert parse_feishu_url(url) == expected


@pytest.mark.parametrize(
    ("url", "match"),
    [
        ("", "为空"),
        ("ftp://example.feishu.cn/docx/abc12345", "https"),
        ("http://example.feishu.cn/docx/abc12345", "https"),
        ("https://evil.com/docx/abc12345", "非飞书域名"),
        ("https://example.feishu.cn.evil.com/docx/abc12345", "非飞书域名"),
        ("https://example.feishu.cn/", "路径段不足"),
        ("https://example.feishu.cn/docx", "路径段不足"),
        ("https://example.feishu.cn/unknown/abc12345", "未支持"),
        ("https://example.feishu.cn/docx/x", "token 长度"),
    ],
)
def test_invalid_urls(url: str, match: str) -> None:
    with pytest.raises(InvalidFeishuURL, match=match):
        parse_feishu_url(url)


def test_non_string_input() -> None:
    with pytest.raises(InvalidFeishuURL, match="为空"):
        parse_feishu_url(None)  # type: ignore[arg-type]
