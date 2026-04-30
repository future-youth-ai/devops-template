"""archive_meeting 单测 — 飞书云文档版."""

from __future__ import annotations

import responses

import archive_meeting
import config_loader


@responses.activate
def test_archive_creates_feishu_doc(tmp_path, monkeypatch):
    """正常流程: 复制模板 → 写入内容 → 返回 URL."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("feishu:\n  doc_template_token: tpl-abc\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()

    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("MEETING_TITLE", "测试会议")
    monkeypatch.setenv("MEETING_DATE", "2026-04-30")
    monkeypatch.setenv("ISSUE_NUMBER", "42")

    # Mock token
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200},
    )
    # Mock copy doc from template
    responses.add(
        responses.POST,
        "https://open.feishu.cn/open-apis/drive/v1/files/copy",
        json={"code": 0, "data": {"file": {"token": "doc-new-123"}}},
    )

    rc = archive_meeting.main()
    assert rc == 0


def test_missing_template_token_returns_error(tmp_path, monkeypatch):
    """缺少 doc_template_token 时应报错."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text('feishu:\n  doc_template_token: ""\n')
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    monkeypatch.setenv("MEETING_TITLE", "x")
    monkeypatch.setenv("MEETING_DATE", "2026-04-30")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_DOC_TEMPLATE_TOKEN", raising=False)
    assert archive_meeting.main() == 2


def test_missing_credentials_returns_error(tmp_path, monkeypatch):
    """缺少飞书凭证时应报错."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("feishu:\n  doc_template_token: tpl-abc\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    monkeypatch.setenv("MEETING_TITLE", "x")
    monkeypatch.setenv("MEETING_DATE", "2026-04-30")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    assert archive_meeting.main() == 2


def test_rejects_path_traversal_in_date(monkeypatch):
    """MEETING_DATE 含非法格式应拒."""
    monkeypatch.setenv("MEETING_DATE", "../../etc/passwd")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    assert archive_meeting.main() == 2


def test_rejects_non_numeric_issue(monkeypatch):
    """ISSUE_NUMBER 必须纯数字."""
    monkeypatch.setenv("MEETING_DATE", "2026-04-23")
    monkeypatch.setenv("ISSUE_NUMBER", "../../99")
    assert archive_meeting.main() == 2
