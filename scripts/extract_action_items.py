"""调 OpenAI-compatible LLM API (DeepSeek 等) 从 transcript 抽取 action items.

设计:
  - 通过环境变量传 transcript + LLM 配置, 避免命令行传巨型字符串
  - 输出 JSON 数组到 GITHUB_OUTPUT 的 action_items key, 也打印 stdout
  - pydantic 校验每个 item, 不合法的过滤掉
  - prompt 严格要求只输出 JSON, 配合 response_format={"type": "json_object"}

环境变量:
  TRANSCRIPT       必需, 会议文字稿
  LLM_API_KEY      必需
  LLM_BASE_URL     可选, 默认 https://api.deepseek.com/v1
  LLM_MODEL        可选, 默认 deepseek-chat
  GITHUB_OUTPUT    workflow 自动设置, 用于多 step 数据传递
"""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

import config_loader

SYSTEM_PROMPT = "你是会议秘书。你只输出 JSON, 不输出任何解释或 markdown 标记。"

USER_PROMPT_TEMPLATE = """从以下会议记录中提取所有"行动项 / 待办 / Action Item"。

要求:
1. 只提取**明确派遣给某人**的具体任务, 不要泛泛之谈或讨论性发言。
2. 输出严格的 JSON 对象, 形如 {{"items": [...]}}。
3. items 数组每个元素含字段:
   - title:        任务标题, 动词开头, ≤30 字
   - description:  补充背景, ≤200 字, 可空
   - assignee_name: 负责人姓名 (从原文找), 没明确指派写空字符串
   - due_date:     截止日期 YYYY-MM-DD, 没说写 null
   - priority:     优先级 P0/P1/P2/P3 (P0=紧急, P1=重要, P2=普通, P3=低优), 根据上下文语气和紧迫程度判断
4. 如果会议没有任何 action item, 返回 {{"items": []}}.

会议记录:
---
{transcript}
---
"""


class ActionItem(BaseModel):
    """单个行动项 (LLM 输出 schema)."""

    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    assignee_name: str = ""
    due_date: str | None = None
    priority: str = Field("P2", pattern=r"^P[0-3]$")


def extract(
    transcript: str,
    api_key: str,
    base_url: str,
    model: str,
) -> list[dict]:
    """调 LLM 抽取 action items, 返回 list[dict] (经过 pydantic 校验)."""
    if not transcript or not transcript.strip():
        print("⚠️ transcript 为空, 跳过 LLM", file=sys.stderr)
        return []

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(transcript=transcript),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=2000,
    )
    raw = resp.choices[0].message.content or '{"items": []}'
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"::error::LLM 输出非合法 JSON: {e}\nraw={raw[:300]}", file=sys.stderr)
        return []

    raw_items = obj.get("items", []) if isinstance(obj, dict) else []
    if not isinstance(raw_items, list):
        return []

    validated: list[dict] = []
    for ri in raw_items:
        if not isinstance(ri, dict):
            continue
        try:
            validated.append(ActionItem(**ri).model_dump())
        except ValidationError as e:
            print(f"⚠️ 跳过格式不对的 item: {ri} ({e})", file=sys.stderr)
    return validated


def main() -> int:
    transcript = os.environ.get("TRANSCRIPT", "")
    api_key = config_loader.get("llm", "api_key", env="LLM_API_KEY")
    base_url = config_loader.get(
        "llm", "base_url", env="LLM_BASE_URL", default="https://api.deepseek.com/v1"
    )
    model = config_loader.get("llm", "model", env="LLM_MODEL", default="deepseek-chat")

    if not api_key:
        print("::error::LLM_API_KEY 未设置", file=sys.stderr)
        return 2

    items = extract(transcript, api_key, base_url, model)
    print(f"提取到 {len(items)} 个 action items")
    print(json.dumps(items, ensure_ascii=False, indent=2))

    # 写 GITHUB_OUTPUT (multi-line via heredoc)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        out_str = json.dumps(items, ensure_ascii=False)
        with open(gh_out, "a") as f:
            f.write(f"action_items<<ACTION_ITEMS_EOF\n{out_str}\nACTION_ITEMS_EOF\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
