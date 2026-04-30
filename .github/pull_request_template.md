<!--
  Commit 消息规范:
    [DEL-xx] 描述               交付物
    [DEL-xx][MVP] 描述          里程碑
    [PHASE-x] 描述              阶段
    feat|fix|refactor: 描述     普通
-->

## 变更说明

<!-- 一句话描述本次 PR 做了什么 -->

## 影响范围

- [ ] `scripts/` — 自动化脚本
- [ ] `.github/` — CI / 仓库配置
- [ ] 文档 / 配置 / 其他

## 类型

- [ ] feat: 新功能
- [ ] fix: Bug 修复
- [ ] refactor: 重构
- [ ] docs: 文档
- [ ] chore: CI / 杂项
- [ ] [DEL-xx] 交付物
- [ ] [PHASE-x] 阶段交付

## 关联

- Issue: #
- 交付物编号: DEL-

## 自检清单

- [ ] `ruff check scripts && ruff format --check scripts` 通过
- [ ] 单元测试通过
- [ ] 未提交 `.env` / secrets / 真实凭证
