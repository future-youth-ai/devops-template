<!--
  Commit 消息规范:
    [DEL-xx] 描述               交付物
    [DEL-xx][MVP] 描述          里程碑
    [PHASE-x] 描述              阶段
    feat|fix|refactor: 描述     普通
-->

## 🎯 变更说明

<!-- 一句话描述本次 PR 做了什么 -->

## 📦 影响的项目

- [ ] `meeting_bot/` — 飞书会议 bot
- [ ] `scripts/` — 仓库级工具
- [ ] `.github/` — CI / 仓库配置
- [ ] 文档 / 其他

## 📋 类型

- [ ] feat: 新功能
- [ ] fix: Bug 修复
- [ ] refactor: 重构
- [ ] perf: 性能
- [ ] docs: 文档
- [ ] test: 测试
- [ ] chore: CI / 杂项
- [ ] [DEL-xx] 交付物
- [ ] [PHASE-x] 阶段交付

## 🔗 关联

- 需求 / Issue: #
- 交付物编号: DEL-
- 设计文档:

## ✅ 自检清单

- [ ] 对应子项目目录下 `ruff check . && ruff format --check .` 通过
- [ ] `mypy src` 通过 (如适用)
- [ ] 单元测试通过, 覆盖率不下降
- [ ] `bandit -c pyproject.toml -r src -ll` 无高危
- [ ] 未提交 `.env` / secrets / 真实凭证 / 会议数据
- [ ] 破坏性变更已在 README / CHANGELOG 声明

## 🔐 安全与合规

<!-- 是否涉及: 用户数据、权限、webhook 验签、外部 API 凭证? -->

## 🧪 测试方法

<!-- 如何验证本次变更 -->
