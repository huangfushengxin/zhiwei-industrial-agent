# 智维 ZHIWEI · 工业设备运维 Agent

[![CI](https://github.com/huangfushengxin/zhiwei-industrial-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/huangfushengxin/zhiwei-industrial-agent/actions/workflows/ci.yml)

面向旋转设备的运维仿真应用：读取传感器数据，检测异常、诊断故障、制定维修方案、模拟维修，并用维修前的健康基线验证结果。未通过验证时重新规划，达到次数上限则报告未解决。

[在线案例展示](https://huangfushengxin.github.io/zhiwei-industrial-agent/) · [演示视频](https://www.bilibili.com/video/BV1MEpn6cExt/) · [完整运行指南](docs/RUNNING.md) · [开发与 PR 约定](CONTRIBUTING.md)

在线展示页是预计算案例，不会在浏览器中调用模型。完整 Agent 使用官方 **Agnes Harness (AGH)** 作为底座，通过本项目编写的 MCP 服务调用工业工具；AGH 不是本人开发的框架。

## 先在自己的电脑运行

只需 Python 3.11+，无需 Key、Node.js 或第三方 Python 依赖：

```sh
git clone https://github.com/huangfushengxin/zhiwei-industrial-agent.git
cd zhiwei-industrial-agent
python app/demo_server.py --mode offline
```

浏览器打开 <http://127.0.0.1:8801/>，选择设备或上传项目提供的 CSV，点击开始。macOS/Linux 如无 `python`，使用 `python3`。

离线模式按固定工具流程计算，不调用大模型；页面明确标注模式。真实自然语言 Agent 请按 [AGH/MCP 配置与启动步骤](docs/RUNNING.md#4-完整-agh--mcp-agent)运行 `--mode agent`。

也可在命令行观察失败后重规划：

```sh
python tools/closed_loop.py data/sensor_overload.csv --repair-effectiveness 0.5 --out-dir artifacts/repairs --summary
```

## 项目能力与代码证据

| 能力 | 本项目的实现 | 直接查看 |
| --- | --- | --- |
| Agent 应用与工具执行 | AGH 承担模型规划与执行；应用提供任务、SOP、工业工具与 SSE 展示 | [演示服务](app/demo_server.py)、[SOP](agent/skills/zhiwei-closed-loop/SKILL.md) |
| MCP / tool use | stdio 服务暴露 9 个工具；只读/写盘分级；真协议自检 | [MCP 服务](agent/mcp/zhiwei_mcp_server.py)、[自检](agent/mcp/verify_mcp_client.py) |
| 失败恢复 | 维修验证失败后重规划，限制重试次数；保留失败 trace | [闭环](tools/closed_loop.py)、[回归测试](tests/test_pipeline.py) |
| LLM API | 可选诊断报告客户端，Bearer 鉴权、超时、有限重试、错误脱敏 | [HTTP 客户端](agent/llm/client.py) |
| Structured output | 模型输出经 Pydantic 严格 Schema 校验，核心字段与工具事实比对；失败纠正一次 | [输出契约](agent/llm/schema.py)、[报告生成](agent/llm/report.py) |
| Context window | 给输出留预算，保留系统规则与当前事实，按完整轮次淘汰最旧历史；必需内容超限则拒绝请求 | [上下文预算](agent/llm/context.py)、[测试](tests/test_context.py) |
| pytest / 自动化 | 工具回归、HTTP/SSE、MCP stdio、模型错误响应与上下文边界 | [测试目录](tests/)、[GitHub Actions](.github/workflows/ci.yml) |
| Docker / 部署 | 无密钥工具演示镜像；另有固定 AGH 提交的 Render 模型部署方案 | [Dockerfile](Dockerfile)、[Render](deploy/render/) |
| Git 协作与 AI 开发 | 分支/PR、检查记录、真实 AI 辅助开发过程；不伪造独立 review | [本次 PR #1](https://github.com/huangfushengxin/zhiwei-industrial-agent/pull/1)、[贡献指南](CONTRIBUTING.md)、[开发记录](docs/AI_DEVELOPMENT.md) |

可选 LLM 报告模块展示应用层 API/输出/上下文处理，是独立诊断报告路径，不声称替代 AGH 的自主 Agent 或实现了新的 Agent 框架。它采用客户端校验，没有假定供应商支持服务端 strict JSON Schema。

## 安装依赖与验证

离线网页本身无需安装依赖。测试、MCP 和可选 LLM 模块使用：

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: . .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/validate.py
```

验收报告与生成页位于 `artifacts/validation/`，历史验收在临时副本运行。pytest 的模型 HTTP 响应来自测试替身，不使用真实 Key。MCP 集成测试会启动真实 stdio 服务并调用全部 9 个工具。

CI 配置覆盖 Ubuntu/Windows × Python 3.11/3.13，以及无密钥 Docker 构建和启动。以页面顶部 badge 和 [Actions 运行记录](https://github.com/huangfushengxin/zhiwei-industrial-agent/actions)的实际状态为准，配置存在不等于全部环境已验证。

历史固定仿真用例：故障诊断 5/5、闭环 6/6、异常恢复 4/4、三案例 3/3。这些是小样本工具验收，不代表真实工业准确率，也不是 LLM eval 分数。

## 可选：直接调用模型生成结构化报告

安装依赖并将自己的 `AGNES_API_KEY` 放入终端环境后：

```sh
python -m agent.llm.report --schema
python -m agent.llm.report data/sensor_bearing_wear.csv --output artifacts/llm-report.json
```

默认模型为 `agnes-3.0-flash`；配置变量见 [.env.example](.env.example)，程序不自动加载该文件。Key 不提交 GitHub。真实调用与自动测试的区别、token 估算限制见 [运行指南](docs/RUNNING.md#5-可选直接调用模型生成结构化诊断报告)。

## 架构与个人贡献

```text
演示网页 / 自然语言任务
          │
          ├─ offline → Python 工具链（无模型）
          │
          └─ agent → Agnes Harness + Agnes 模型（第三方）
                         │ MCP stdio
                         ▼
                 智维 MCP 服务（9 工具）
                         │
          读取 → 检测 → 诊断 → 方案 → 模拟维修 → 验证
                                      ▲            │
                                      └─ 未通过重规划 ┘

可选报告：工具诊断事实 → 上下文预算 → 模型 API → Schema/事实校验
```

本人负责应用问题定义、仿真数据生成、异常检测与故障匹配、维修/验证工具、MCP 服务、SOP、展示后端和前端，以及本仓库的测试与运行文档。开发使用 AI 辅助，过程见 [记录](docs/AI_DEVELOPMENT.md)。

AGH 负责模型路由、底层 Agent 执行、资源管理与审批；MCP SDK 提供协议实现，Pydantic 提供校验。这些第三方能力不计为本人从零实现。

一个关键决策是维修后复测始终参照维修前的健康基线，避免把“从复测第一秒就存在的残留故障”误当正常。参见 [维修验证](tools/verify_repair.py)与对应回归测试。

## Docker 快速体验

```sh
docker build -t zhiwei-offline .
docker run --rm -p 8801:8801 zhiwei-offline
```

此镜像运行离线工具，不需要模型密钥。完整模型云部署另见 [Render 指南](deploy/render/README.md)；它需要单独验证模型、MCP 和 Agent 执行，不以离线镜像通过代替。

## 项目背景与边界

本项目源于 2026 年江苏省 AI+科学与工程创新实践黑客松（本科生组，U225，SoloAI Lab）。比赛原始说明保留在 [赛事文档](docs/HACKATHON.md)，历史模型会话与验收材料在 [evidence/](evidence/)。历史记录不等于当前版本已重新完成真实模型测试。

数据全部为程序生成的仿真数据，维修也是文件级模拟。项目不控制真实设备；现场准确率、真实模型效果评测和生产部署仍需要进一步验证。PDF/OCR、3D 建模、独立开发 AGH 等未实现能力不写成已有经验。

原创代码采用 [Apache-2.0](LICENSE)；第三方来源见 [说明](docs/第三方素材来源说明.md)。
