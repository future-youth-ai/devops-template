"""config_loader 单测."""
from __future__ import annotations

import config_loader


def test_load_config_from_file(tmp_path, monkeypatch):
    """config.yml 能正常加载."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("project:\n  name: test-proj\nfeishu:\n  bitable_app_token: tok-123\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    cfg = config_loader.load_config()
    assert cfg["project"]["name"] == "test-proj"
    assert cfg["feishu"]["bitable_app_token"] == "tok-123"


def test_get_with_env_override(tmp_path, monkeypatch):
    """环境变量优先于 config.yml."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("feishu:\n  bitable_app_token: from-file\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "from-env")
    val = config_loader.get("feishu", "bitable_app_token", env="FEISHU_BITABLE_APP_TOKEN")
    assert val == "from-env"


def test_get_falls_back_to_config(tmp_path, monkeypatch):
    """无环境变量时回退到 config.yml."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("feishu:\n  bitable_app_token: from-file\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    val = config_loader.get("feishu", "bitable_app_token", env="FEISHU_BITABLE_APP_TOKEN")
    assert val == "from-file"


def test_get_returns_default_when_missing(tmp_path, monkeypatch):
    """section/key 不存在时返回 default."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("project:\n  name: x\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    val = config_loader.get("nonexistent", "key", default="fallback")
    assert val == "fallback"


def test_config_caches_after_first_load(tmp_path, monkeypatch):
    """config 只读一次文件."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("project:\n  name: v1\n")
    monkeypatch.setattr(config_loader, "CONFIG_PATH", cfg_file)
    config_loader._cache.clear()
    cfg1 = config_loader.load_config()
    cfg_file.write_text("project:\n  name: v2\n")
    cfg2 = config_loader.load_config()
    assert cfg1 is cfg2  # same object, cached
