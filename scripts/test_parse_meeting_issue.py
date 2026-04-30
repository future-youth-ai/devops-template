"""parse_meeting_issue 单测."""

from __future__ import annotations

from parse_meeting_issue import extract_field

SAMPLE_BODY = """### 会议标题

4月23日 项目立项会

### 会议日期 (YYYY-MM-DD)

2026-04-23

### 飞书链接 (妙记/Docx/Wiki)

https://meetings.feishu.cn/minutes/abc123xyz

### 备注 (可选)

_No response_
"""


def test_extract_normal_field() -> None:
    assert extract_field(SAMPLE_BODY, "会议标题") == "4月23日 项目立项会"
    assert extract_field(SAMPLE_BODY, "会议日期 (YYYY-MM-DD)") == "2026-04-23"
    assert (
        extract_field(SAMPLE_BODY, "飞书链接 (妙记/Docx/Wiki)")
        == "https://meetings.feishu.cn/minutes/abc123xyz"
    )


def test_extract_no_response_returns_empty() -> None:
    assert extract_field(SAMPLE_BODY, "备注 (可选)") == ""


def test_extract_missing_field() -> None:
    assert extract_field(SAMPLE_BODY, "不存在的字段") == ""


def test_extract_empty_body() -> None:
    assert extract_field("", "会议标题") == ""
