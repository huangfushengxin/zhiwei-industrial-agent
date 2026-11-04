# 开发与真实协作记录

```sh
git switch -c feature/describe-your-change
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/validate.py
git diff --check
```

提交 focused commits，推送分支并创建 PR。说明触发问题、修改后的行为、实际执行的测试和未验证环境。通过 Actions 后再 review/合并；不要伪造多人协作、独立 review 或真实模型效果。

新增行为至少覆盖关键正常路径和失败路径。HTTP 模型测试默认注入替身，不读取真实 Key；文件写入使用临时目录；MCP 集成测试运行真实 stdio 服务。原始 `data/` 仿真样本用于回归，运行产物写 `artifacts/`。

review 重点：未经验证是否声称修好、结构化输出是否允许额外字段或矛盾事实、上下文是否丢掉规则/当前证据、错误日志是否包含凭据、README 是否能让首次访问者跑起来。

项目使用 AI 辅助开发。AI 生成的代码仍须经实际测试与人工理解后使用，参见 [AI 开发记录](docs/AI_DEVELOPMENT.md)。PR 中的自查和 CI 不等同于独立人工 review。
