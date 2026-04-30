"""extract_action_items 单测 - mock OpenAI 客户端."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from extract_action_items import extract


def _mock_client(json_response: str) -> MagicMock:
    """构造 mock client.chat.completions.create 返回."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = json_response
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


@patch("extract_action_items.OpenAI")
def test_extract_normal_response(mock_openai_class: MagicMock) -> None:
    mock_openai_class.return_value = _mock_client(
        json.dumps(
            {
                "items": [
                    {
                        "title": "实现登录",
                        "assignee_name": "张三",
                        "due_date": "2026-04-30",
                    },
                    {
                        "title": "写文档",
                        "description": "API 文档",
                        "assignee_name": "李四",
                    },
                ]
            }
        )
    )
    items = extract("会议内容", "k", "u", "m")
    assert len(items) == 2
    assert items[0]["title"] == "实现登录"
    assert items[0]["due_date"] == "2026-04-30"
    assert items[1]["due_date"] is None


@patch("extract_action_items.OpenAI")
def test_extract_empty_transcript_skips_llm_call(mock_openai_class: MagicMock) -> None:
    items = extract("", "k", "u", "m")
    assert items == []
    mock_openai_class.assert_not_called()


@patch("extract_action_items.OpenAI")
def test_extract_filters_invalid_items(mock_openai_class: MagicMock) -> None:
    mock_openai_class.return_value = _mock_client(
        json.dumps(
            {
                "items": [
                    {"title": "正常", "assignee_name": "x"},
                    {"title": "", "assignee_name": "y"},  # title 太短, 被过滤
                    {"description": "no title"},  # 缺必填 title
                    "not a dict at all",  # 非 dict
                ]
            }
        )
    )
    items = extract("xxx", "k", "u", "m")
    assert len(items) == 1
    assert items[0]["title"] == "正常"


@patch("extract_action_items.OpenAI")
def test_extract_no_items_key_returns_empty(mock_openai_class: MagicMock) -> None:
    mock_openai_class.return_value = _mock_client('{"foo": "bar"}')
    assert extract("xxx", "k", "u", "m") == []


@patch("extract_action_items.OpenAI")
def test_extract_invalid_json_returns_empty(mock_openai_class: MagicMock) -> None:
    mock_openai_class.return_value = _mock_client("这不是 JSON")
    assert extract("xxx", "k", "u", "m") == []


@patch("extract_action_items.OpenAI")
def test_extract_items_not_a_list(mock_openai_class: MagicMock) -> None:
    mock_openai_class.return_value = _mock_client('{"items": "not a list"}')
    assert extract("xxx", "k", "u", "m") == []
