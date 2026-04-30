# devops-template

> GitHub 仓库 DevOps 自动化模板 — CI / commit 规范 / 飞书同步 / 会议自动化 / AI 代码审查

从这个模板创建仓库，编辑 `config.yml`，即可获得全套自动化能力。

## 你能得到什么

| 功能 | 说明 |
|------|------|
| **CI (Ruff lint)** | push / PR 自动运行 Ruff check + format，ci-gate 汇总结果 |
| **Commit 规范校验** | PR 中所有 commit 必须符合 conventional commit 或 `[DEL-xx]` / `[PHASE-x]` 格式 |
| **飞书交付同步** | push 到 main 的 `[DEL-xx]` / `[PHASE-x]` commit 自动写入飞书多维表格 + 群通知 |
| **飞书任务状态** | commit 中的 `[TASK-xxx]` / `[DONE-TASK-xxx]` 自动推进飞书任务进展状态 |
| **会议自动化** | Issue 表单提交会议链接 → 拉取转写 → LLM 提取行动项 → 飞书建任务 → 归档到飞书云文档 |
| **CodeRabbit → 飞书** | CodeRabbit 审查摘要和结论自动转发到飞书群 |
| **Secret 扫描** | TruffleHog 在 PR 中扫描泄漏的密钥 |
| **PR 自动标签** | 按变更路径自动给 PR 打 `area/*` 标签 |

## 快速开始

1. 点击 **Use this template** → 创建新仓库
2. 编辑 `config.yml` — 填入飞书多维表格 token 和 table ID
3. (可选) 在仓库 Settings → Secrets 添加仓库级 Secrets 覆盖组织默认值
4. (可选) 安装 [CodeRabbit](https://github.com/apps/coderabbitai) GitHub App 启用 AI 代码审查
5. Done — push 代码即可触发全部自动化

## config.yml 配置说明

```yaml
project:
  name: "my-project"           # 项目名称，用于飞书通知卡片标题
  language: "python"            # 主语言 (MVP 仅支持 python)

feishu:
  bitable_app_token: ""         # 飞书多维表格 → 地址栏 /base/<这个值>
  bitable_table_id: ""          # 多维表格 → 表格 URL 中 table= 后的值
  summary_chat_id: ""           # 飞书群 → 群设置 → 群 chat_id
  doc_template_token: ""        # 飞书云文档模板 → 地址栏 /docx/<这个值>

llm:
  base_url: "https://api.deepseek.com/v1"  # OpenAI-compatible API 地址
  model: "deepseek-chat"                    # 模型名称

commit:
  delivery_tracking: true       # 启用 [DEL-xx] / [PHASE-x] 交付物追踪
  task_sync: true               # 启用 [TASK-xxx] 飞书任务状态同步
  extra_types: []               # 额外允许的 conventional commit types, 如 ["wip"]
```

**密钥不写在 config.yml 中**，通过 GitHub Secrets 注入（org-level 或仓库级）：

| Secret 名称 | 用途 |
|---|---|
| `FEISHU_APP_ID` | 飞书自建应用 App ID |
| `FEISHU_APP_SECRET` | 飞书自建应用 App Secret |
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 Webhook 地址 |
| `FEISHU_WEBHOOK_SECRET` | (可选) Webhook 签名校验密钥 |
| `DEEPSEEK_API_KEY` | LLM API Key (会议行动项提取) |

## Commit 提交规范

| 格式 | 用途 | 示例 |
|------|------|------|
| `type: 描述` | 普通提交 | `feat: 实现用户登录` |
| `type(scope): 描述` | 带范围 | `fix(api): 修复超时问题` |
| `[DEL-xx] 描述` | 交付物完成 | `[DEL-04] 文档解析器完成` |
| `[DEL-xx][MVP] 描述` | 里程碑达成 | `[DEL-07][MVP] AI 审核引擎可用` |
| `[PHASE-x] 描述` | 阶段完成 | `[PHASE-1] Phase 1 全部交付完成` |

可选尾标签：`[TASK-recXXX]`（推进任务状态）或 `[DONE-TASK-recXXX]`（完成任务）。

允许的 type：`feat` `fix` `docs` `style` `refactor` `perf` `test` `chore` `build` `ci` `revert`。可通过 `config.yml` 的 `commit.extra_types` 添加自定义 type。

## 各 Workflow 说明

### ci.yml
- **触发**: push 到 main/dev，或 PR 到 main/dev
- **作用**: Ruff lint + format check → ci-gate 汇总

### commit-lint.yml
- **触发**: PR 到 main/dev
- **作用**: 校验 PR 中每条 commit 消息是否符合上述规范

### feishu-sync.yml
- **触发**: push 到 main 且 commit 含 `[DEL-]` / `[PHASE-]` / `[TASK-]`
- **作用**: 写入飞书多维表格 + 发送群通知卡片 + 推进任务状态

### process-meeting.yml
- **触发**: meeting label 的 Issue opened / labeled / closed
- **作用**: 解析 issue 表单 → 拉飞书转写 → LLM 提取行动项 → 创建飞书任务 → 归档到飞书云文档

### coderabbit-report-sync.yml
- **触发**: CodeRabbit bot 的 issue_comment 或 pull_request_review
- **作用**: 将审查摘要和结论转发到飞书群

### secret-scan.yml
- **触发**: PR
- **作用**: TruffleHog 扫描凭证泄漏

### labeler.yml
- **触发**: PR
- **作用**: 按变更路径自动打标签

## 添加你自己的项目 CI

在 `.github/workflows/ci.yml` 的 `needs` 中添加你的 job：

```yaml
jobs:
  # ... 已有的 scripts-lint ...

  my-project-test:
    name: my-project / Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest my_project/

  ci-gate:
    needs: [scripts-lint, my-project-test]  # 加入新 job
    # ...
```

## Org-level Secrets 设置指南

> 管理员操作，整个组织只需做一次。

1. 进入 GitHub 组织 Settings → Secrets and variables → Actions
2. 添加以下 Organization secrets：
   - `FEISHU_APP_ID` — 飞书开放平台 → 应用管理 → App ID
   - `FEISHU_APP_SECRET` — 同上 → App Secret
   - `FEISHU_WEBHOOK_URL` — 飞书群 → 群设置 → 群机器人 → 自定义机器人 → Webhook 地址
   - `DEEPSEEK_API_KEY` — DeepSeek 开放平台 API Key
3. Secret 的 Repository access 设为 "All repositories" 或选择指定仓库
4. 从模板创建的仓库会自动继承这些 Secrets

## FAQ

**Q: 如何在仓库级覆盖组织 Secret？**
在仓库 Settings → Secrets 中添加同名 Secret，仓库级会自动覆盖组织级。

**Q: 如何禁用某个功能？**
删除对应的 workflow 文件即可。例如不需要会议自动化，删除 `process-meeting.yml`。

**Q: CodeRabbit 如何安装？**
访问 [github.com/apps/coderabbitai](https://github.com/apps/coderabbitai)，安装到你的仓库。`.coderabbit.yaml` 已预配好审查规则。

**Q: 如何添加自定义 commit type？**
在 `config.yml` 中设置 `commit.extra_types: ["wip", "release"]`。

**Q: config.yml 中的值和环境变量冲突时谁优先？**
环境变量 (GitHub Secrets) 优先于 config.yml。
