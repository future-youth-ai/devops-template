"""统一配置加载器.

读取优先级: 环境变量 > config.yml > 默认值.
config.yml 只读一次, 结果缓存在模块级变量中.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _REPO_ROOT / "config.yml"
_cache: dict[str, Any] = {}


def load_config() -> dict[str, Any]:
    """读取 config.yml, 结果缓存."""
    if "data" in _cache:
        return _cache["data"]
    if not CONFIG_PATH.exists():
        print(f"::warning::config.yml 不存在 ({CONFIG_PATH}), 使用空配置", file=sys.stderr)
        _cache["data"] = {}
        return _cache["data"]
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as e:
        print(f"::warning::config.yml 解析失败: {e}", file=sys.stderr)
        data = {}
    _cache["data"] = data
    return data


def get(section: str, key: str, *, env: str = "", default: Any = "") -> Any:
    """获取配置值. 环境变量 > config.yml > default."""
    if env:
        env_val = os.environ.get(env)
        if env_val:
            return env_val
    cfg = load_config()
    return cfg.get(section, {}).get(key, default)
