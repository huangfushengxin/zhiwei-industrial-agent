# 本次 AI 辅助工程迭代记录

日期：2026-11-04。需求：补齐首次运行、岗位工程证据和求职 README。使用 Codex 辅助读取代码、实现、设计回归测试与自查；项目所有者负责理解、维护与面试解释。没有虚构其他开发者或独立 reviewer。

## 从问题到验证

| 观察到的问题 | 实现决策 | 验证证据 |
| --- | --- | --- |
| 首次运行依赖 AGH 与个人账号配置 | 默认提供无需依赖/密钥的离线工具模式，保留显式 Agent 模式 | 本地 HTTP 上传 + SSE 完成测试，禁止启动模型子进程 |
| MCP 自检遇到工具失败仍可能最后宣称全部通过 | 累计工具错误并返回失败退出码 | MCP 真 stdio 九工具自检；失败退出码回归测试 |
| `max_attempts=0` 会导致读取空 attempts 列表 | 入口拒绝无效次数和修复范围 | 非法参数、达到次数仍未修好的测试 |
| 工具 JSON 不足以证明模型结构化输出 | 新增独立模型报告客户端、严格 Schema 与核心事实校验 | 畸形 JSON、多余字段、矛盾故障、二次纠正失败测试 |
| 只有底座上下文配置，缺少应用侧策略 | 保留必需规则/事实，按完整轮次淘汰最旧历史 | 中文预算、整轮淘汰、过大证据在请求前拒绝测试 |
| 测试可能依赖作者环境或覆盖数据 | 独立 venv、临时副本验收、Windows/Linux CI | pytest XML、验收 JSON、依赖清单作为 Actions artifacts |

## 使用 AI 的工作方法

1. 先核对公开仓库文件和执行基线，不把 README 的百分比当成验证结果。
2. 读取现有工具函数、AGH 的当前文档和 CLI 约定，保留第三方底座归属。
3. 将需求拆成可检查的行为：不带 Key 能否完成演示、错误输出能否被拒绝、MCP 实际是否可调用。
4. 编写实现与边界测试，实际运行后根据错误修正。Windows 沙箱曾阻止临时目录、HTTP/管道测试；在允许本地子进程的环境重跑，不用跳过测试掩盖它。
5. 检查最终 diff、凭据和文件产物，将真实分支、PR、CI 结果保留在 GitHub。

## 证据边界

本地验证（Windows，Python 3.13.7，独立 venv）：

- `python -m pytest --junitxml=artifacts/pytest.xml`：49 passed。
- `python scripts/validate.py`：5/5、6/6、4/4、3/3，全部通过。
- `python -m compileall -q agent app tools scripts tests` 与 `git diff --check`：通过。
- README/运行指南/贡献指南的本地文件链接：检查通过。

Linux、Python 3.11、Docker 由 GitHub Actions 验证，以实际 run 为准；本机未安装 Docker。模型报告本次未进行付费真实 API 调用。

`tests/test_llm.py` 中的响应由测试替身生成，不是实际模型效果；没有将这些结果计为 LLM eval 分数。原来的 5/5、6/6、4/4、3/3 是固定仿真用例的工具验收，不代表真实工业数据表现。
完整 AGH 云部署、真实模型成功率以及独立人工 review，只有出现相应运行/审核记录后才能宣称完成。自动检查和作者自查应各自注明身份。

实现参考：[pytest 临时目录](https://docs.pytest.org/en/stable/how-to/tmp_path.html)、[GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)、[Pydantic JSON 校验](https://docs.pydantic.dev/latest/concepts/json/)。AGH 注册与 Skill 流程以 [RUNNING.md](RUNNING.md)中固定提交的官方文档为准。
