"""_blocks_to_text 单测 - 纯逻辑, 无外部依赖."""

from __future__ import annotations

from feishu_content import _blocks_to_text


def _make_block(block_type: int, field_name: str, text: str) -> dict:
    """Helper: 构造一个飞书 docx block."""
    return {
        "block_type": block_type,
        field_name: {"elements": [{"text_run": {"content": text}}]},
    }


def test_text_and_heading() -> None:
    blocks = [
        _make_block(3, "heading1", "标题一"),
        _make_block(2, "text", "段落一"),
    ]
    text = _blocks_to_text(blocks)
    assert "# 标题一" in text
    assert "段落一" in text


def test_bullet_and_ordered() -> None:
    blocks = [
        _make_block(12, "bullet", "无序项"),
        _make_block(13, "ordered", "有序项"),
    ]
    text = _blocks_to_text(blocks)
    assert "- 无序项" in text
    assert "1. 有序项" in text


def test_todo() -> None:
    blocks = [_make_block(17, "todo", "买牛奶")]
    assert "- [ ] 买牛奶" in _blocks_to_text(blocks)


def test_quote_and_quote_container() -> None:
    blocks = [
        _make_block(15, "quote", "引用文字"),
        _make_block(22, "quote_container", "容器引用"),
    ]
    text = _blocks_to_text(blocks)
    assert "> 引用文字" in text
    assert "> 容器引用" in text


def test_code_fenced() -> None:
    blocks = [_make_block(14, "code", "print('hello')")]
    text = _blocks_to_text(blocks)
    assert "```\nprint('hello')\n```" in text


def test_callout() -> None:
    blocks = [_make_block(19, "callout", "注意事项")]
    assert "注意事项" in _blocks_to_text(blocks)


def test_page_root_skipped() -> None:
    """block_type=1 (page 根容器) 应被跳过."""
    blocks = [
        {"block_type": 1, "page": {"elements": [{"text_run": {"content": "root"}}]}},
        _make_block(2, "text", "正文"),
    ]
    text = _blocks_to_text(blocks)
    assert "root" not in text
    assert "正文" in text


def test_unknown_type_fallback() -> None:
    """未知 block_type 仍保留文字, 无前缀."""
    blocks = [_make_block(999, "mystery", "神秘内容")]
    text = _blocks_to_text(blocks)
    assert "神秘内容" in text
    assert text.strip() == "神秘内容"


def test_empty_text_skipped() -> None:
    """空文字 block 不出现在输出里."""
    blocks = [_make_block(2, "text", "   ")]
    assert _blocks_to_text(blocks) == ""


def test_mixed_block_types() -> None:
    """模拟真实文档: heading + text + bullet + todo 混合."""
    blocks = [
        {"block_type": 1, "page": {"elements": []}},
        _make_block(3, "heading1", "会议纪要"),
        _make_block(2, "text", "2026年4月16日"),
        _make_block(12, "bullet", "讨论了CI/CD流程"),
        _make_block(12, "bullet", "飞书任务自动同步"),
        _make_block(17, "todo", "完成MCP配置"),
        _make_block(17, "todo", "编写ONBOARDING文档"),
    ]
    text = _blocks_to_text(blocks)
    assert "# 会议纪要" in text
    assert "2026年4月16日" in text
    assert "- 讨论了CI/CD流程" in text
    assert "- 飞书任务自动同步" in text
    assert "- [ ] 完成MCP配置" in text
    assert "- [ ] 编写ONBOARDING文档" in text
