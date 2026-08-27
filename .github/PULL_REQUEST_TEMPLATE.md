## Summary / 变更摘要

<!-- What does this PR do? One or two sentences. / 这个 PR 做了什么？一两句话说明。 -->

Closes #<!-- issue number / 关联的 Issue 编号 -->

## Motivation / 背景

<!-- Why is this change needed? Link the issue if there is one. / 为什么需要这个变更？如有 Issue 请关联。 -->

## Type of change / 变更类型

- [ ] Bug fix / 缺陷修复
- [ ] New feature / 新功能
- [ ] Refactor / 重构
- [ ] Docs / 文档
- [ ] Config / CI / 配置 / CI
- [ ] Other / 其他: <!-- specify / 请说明 -->

## Testing / 测试

Run the checks for the modules you touched, and describe what you verified manually.
运行你所改动模块对应的检查，并说明手动验证了什么。

- [ ] Backend tests / 后端测试: `cd backend/api && uv run python -m unittest discover -s tests`
- [ ] TUI tests / TUI 测试: `cd frontend/tui && uv run python -m unittest discover -s tests`
- [ ] Web typecheck & build / Web 类型检查与构建: `cd frontend/web && pnpm typecheck && pnpm build`
- [ ] Manual verification / 手动验证:
  <!-- e.g. "started with ./scripts/start.sh, created a task, verified tool audit entries" /
       例如：“./scripts/start.sh 启动，创建任务，确认工具审计记录” -->

## Checklist / 检查清单

- [ ] No secrets, `.env` files, or real credentials included / 未包含密钥、`.env` 文件或真实凭据
- [ ] Commit messages follow the convention in [CONTRIBUTING.md](CONTRIBUTING.md) / Commit 遵循 [CONTRIBUTING.md](CONTRIBUTING.md) 中的规范
- [ ] Docs updated if behavior changed (README / docs/) / 行为变更时已更新文档（README / docs/）
- [ ] No changes to unrelated modules / 未改动无关模块
