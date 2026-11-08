# Contributing

## 协作训练

训练入口和实验提交要求见 [模型训练协作](docs/training/collaboration.md)。
克隆仓库可获得前后端、推理服务和训练脚本；数据集及模型权重不在 Git 中，需要按训练说明单独准备。
先用 GitHub Issue 记录任务，维护 `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human` 或 `wontfix` 标签。修改前从最新 `main` 新建分支，完成后提交 Pull Request。实验结果放在 `docs/experiments/`，不要把原始图片、视频或完整训练目录推送上来。

## Branch and commit rules

- `main` must stay runnable.
- Use short-lived branches for substantial changes.
- Commit messages use `type(scope): summary`, for example `feat(api): add camera probe endpoint`.
- Do not commit secrets, model weights, real camera URLs, phone numbers, or private monitoring footage.

PR 关联对应 Issue，记录实际执行的验证及未测范围。合并后删除已合并的工作分支，不重写共享分支历史。清理前检查引用；缓存可以删除，模型、数据和独有实验记录保留。

当前状态统一维护在 `docs/project/STATUS.md`。旧计划注明日期和替代入口，代码放在 `ml/scripts/`，实验输出放在 `docs/experiments/`，本地模型放在已忽略的 `models/`。

## Definition of done

A change is complete only when it includes the relevant implementation, contract update, tests, migration/configuration, and documentation.

## Required checks

- Web: typecheck, unit tests, production build.
- API: unit/integration tests and Flyway validation.
- Inference: schema tests and deterministic replay tests.
- Contracts: JSON Schema validation and OpenAPI parse.
