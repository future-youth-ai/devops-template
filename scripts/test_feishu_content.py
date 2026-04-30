"""feishu_content 单测 - 用 responses 库 mock HTTP."""

from __future__ import annotations

import pytest
import responses

from feishu_content import (
    FeishuFetchError,
    fetch_content,
    fetch_docx,
    get_tenant_token,
)


@responses.activate
def test_get_tenant_token_ok() -> None:
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    assert get_tenant_token("app", "secret") == "t-abc"


@responses.activate
def test_get_tenant_token_failure() -> None:
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 99991663, "msg": "app ticket invalid"},
    )
    with pytest.raises(FeishuFetchError, match="app ticket invalid"):
        get_tenant_token("app", "secret")


@responses.activate
def test_fetch_minutes_concat_segments() -> None:
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/minutes/v1/minutes/mtk/transcript",
        json={
            "code": 0,
            "data": {
                "transcripts": [
                    {"speaker_name": "Alice", "text": "Hello"},
                    {"speaker_name": "Bob", "sentence": "World"},
                    {"speaker_name": "Alice", "content": "Goodbye"},
                ]
            },
        },
    )
    text = fetch_content("minutes", "mtk", "t-abc")
    assert "[Alice] Hello" in text
    assert "[Bob] World" in text
    assert "[Alice] Goodbye" in text


@responses.activate
def test_fetch_docx_text_blocks() -> None:
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/docx/v1/documents/doc1/blocks",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "block_type": 3,  # heading 1
                        "heading1": {"elements": [{"text_run": {"content": "标题一"}}]},
                    },
                    {
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": "段落一"}}]},
                    },
                    {
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": "段落二"}}]},
                    },
                ],
                "has_more": False,
            },
        },
    )
    text = fetch_content("docx", "doc1", "t-abc")
    assert "# 标题一" in text
    assert "段落一" in text
    assert "段落二" in text


@responses.activate
def test_fetch_docx_paginates() -> None:
    """两页, 验证 page_token 正确传递, has_more 正确处理."""
    # 第一页 has_more=True + page_token
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/docx/v1/documents/doc1/blocks",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": "page1"}}]},
                    }
                ],
                "has_more": True,
                "page_token": "pt-2",
            },
        },
    )
    # 第二页 has_more=False
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/docx/v1/documents/doc1/blocks",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": "page2"}}]},
                    }
                ],
                "has_more": False,
            },
        },
    )
    text = fetch_docx("t-abc", "doc1")
    assert "page1" in text and "page2" in text
    assert len(responses.calls) == 2
    # 第二次请求必须带 page_token=pt-2
    assert "page_token=pt-2" in responses.calls[-1].request.url


@responses.activate
def test_fetch_wiki_resolves_to_docx() -> None:
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node",
        json={
            "code": 0,
            "data": {"node": {"obj_type": "docx", "obj_token": "doc1"}},
        },
    )
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/docx/v1/documents/doc1/blocks",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": "wiki里"}}]},
                    }
                ],
                "has_more": False,
            },
        },
    )
    text = fetch_content("wiki", "wikxxx", "t-abc")
    assert "wiki里" in text


@responses.activate
def test_unknown_kind_raises() -> None:
    with pytest.raises(FeishuFetchError, match="未知 kind"):
        fetch_content("xxx", "tok", "t-abc")


@responses.activate
def test_api_code_nonzero_raises() -> None:
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/minutes/v1/minutes/mtk/transcript",
        json={"code": 99991672, "msg": "permission denied"},
    )
    with pytest.raises(FeishuFetchError, match="permission denied"):
        fetch_content("minutes", "mtk", "t-abc")


@responses.activate
def test_wiki_unsupported_obj_type_raises() -> None:
    responses.add(
        responses.GET,
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node",
        json={
            "code": 0,
            "data": {"node": {"obj_type": "sheet", "obj_token": "sheet1"}},
        },
    )
    with pytest.raises(FeishuFetchError, match="未支持的 obj_type"):
        fetch_content("wiki", "wikxxx", "t-abc")
