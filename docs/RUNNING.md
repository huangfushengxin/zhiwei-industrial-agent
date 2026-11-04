# 从下载到运行

## 1. 获取项目

```sh
git clone https://github.com/huangfushengxin/zhiwei-industrial-agent.git
cd zhiwei-industrial-agent
python --version
```

Python 3.11+。macOS/Linux 若没有 `python`，以下命令使用 `python3`。

## 2. 无密钥演示：先验证工具链

```sh
python app/demo_server.py --mode offline
```

打开 <http://127.0.0.1:8801/>，选择设备，点击“开始智能诊断”。可以上传传感器 CSV；示例在 `data/test/`。
此模式只用 Python 标准库，按固定流程完成检测、诊断、模拟维修和验证；不安装 AGH，不调用模型，不需要 API Key。
页面会明确显示“未调用”。自定义自然语言任务仅在 Agent 模式生效。

也可直接运行闭环并生成 trace：

```sh
python tools/closed_loop.py data/sensor_overload.csv --repair-effectiveness 0.5 --out-dir artifacts/repairs --summary
```

第一次模拟维修不彻底，验证后重新规划，第二次复验。全部操作针对仿真文件，不连接真实工业设备。
本地启动默认仅绑定 `127.0.0.1`。服务是演示用途，没有生产级身份认证或多租户隔离。

## 3. 安装测试、MCP 和可选报告依赖

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

macOS/Linux：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

若 PowerShell 不允许激活，直接把后续 `python` 替换成 `.\.venv\Scripts\python.exe`，无需更改系统执行策略。
只运行 MCP/可选 LLM 报告时安装 `requirements.txt` 即可。MCP SDK 固定为 2.3.0；Pydantic 与 pytest 限定兼容主版本，CI artifact 记录本次解析的完整依赖版本。

```sh
python -m pytest
python scripts/validate.py
python agent/mcp/verify_mcp_client.py
```

以上均不需要密钥。pytest 包含真实本地 HTTP/SSE 和 MCP stdio 测试；LLM HTTP 使用测试替身，不会访问模型服务。
历史验收在临时副本执行，JSON 报告和展示页写到 `artifacts/validation/`，不覆盖原始数据。
直接运行 MCP 自检会生成 `data/repairs/` 复测文件；要保持工作区完全不变，请使用 pytest 中的 MCP 测试。

## 4. 完整 AGH + MCP Agent

这条路径才会调用模型。需要有效的 Agnes 模型账号；离线验收成功不代表这条路径也已成功。

### 4.1 构建官方底座

将 AGH 放在项目同级目录，使用下面固定提交，避免上游默认分支持续变化：

```sh
cd ..
git clone https://github.com/AgnesAI-Labs/agnes-harness.git
cd agnes-harness
git checkout cde816b88c737b9fd04e7ef55b899e7b4cd55eb7
corepack prepare pnpm@10.34.5 --activate
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @agnes/cli build:local
node packages/cli/dist/local/agnes.mjs --help
```

要求 Node.js >=24.10、pnpm 10.34.5。Windows 原生模块需要 Visual Studio C++ Build Tools 与 Windows SDK；构建前按 [AGH 安装文档](https://github.com/AgnesAI-Labs/agnes-harness/blob/cde816b88c737b9fd04e7ef55b899e7b4cd55eb7/docs/guide/install.zh-CN.md)准备 Node headers。Linux 命令沙箱需要 bubblewrap 与可用的 user namespace。

启动工作台，保持该终端运行：

```sh
node packages/cli/dist/local/agnes.mjs serve --port 4180 --profile local-dev
```

打开终端输出的地址。在 Provider 设置中选择 Agnes AI，Base URL 为 `https://api.agnes-ai.cn/v1`，输入自己的 Key，测试连接、选择 `agnes-3.0-flash` 并保存。不要把 Key 写入仓库。

### 4.2 注册 MCP 与工作区 Skill

新终端进入本项目，使用第 3 节的虚拟环境，然后执行：

```sh
python scripts/setup_agh.py --agh-home ../agnes-harness --profile local-dev --register-mcp
```

脚本使用当前 Python 的绝对路径注册 9 个工具，并把项目 SOP 复制到本项目 `.agh/skills/zhiwei-closed-loop/`。它不会修改你的模型账号，也不会自动放开全局审批。
若已经注册过 `zhiwei-ops`，不要重复添加；在工作台检查已有定义的 Python 路径、服务脚本路径和工具范围。仅复制 Skill 可去掉 `--register-mcp`。

在 AGH 工作台中：

1. 为本项目创建会话，工作目录选择 `zhiwei-industrial-agent` 的绝对路径。
2. 在该工作区的 Skills 管理中刷新，检查 `zhiwei-closed-loop` 的来源与内容，点击启用；确认 `trust=trusted`、`desired=enabled`、`actual=ready` 且为 `winner`。
3. 在 MCP 设置中检查并启用 `zhiwei-ops`，确认实际连接 `ready`，工具数为 9。
4. 写盘工具只生成仿真复测文件；出现审批时，按本次任务范围授权。不要将“已注册”当成“已连接”。

参考 [AGH Skill 说明](https://github.com/AgnesAI-Labs/agnes-harness/blob/cde816b88c737b9fd04e7ef55b899e7b4cd55eb7/docs/guide/skills.zh-CN.md)与 [MCP 说明](https://github.com/AgnesAI-Labs/agnes-harness/blob/cde816b88c737b9fd04e7ef55b899e7b4cd55eb7/docs/guide/mcp.zh-CN.md)。CLI 手动 trust/enable 要先用 `mcp get zhiwei-ops` 读取最新 revision，每次写入后重新读取，不能照抄旧 revision。

### 4.3 运行真实 Agent

保持相同的 `AGH_HOME`（如有自定义）与 profile，在项目根目录：

```sh
python app/demo_server.py --mode agent
```

若 AGH 不在同级目录，设置 `ZHIWEI_AGH_HOME` 为 AGH **源码目录**；它与 AGH 保存账号数据的 `AGH_HOME` 是不同变量。profile 可用 `ZHIWEI_AGH_PROFILE` 指定，默认 `local-dev`。
模型密钥由 AGH 的安全配置保存，仅设置报告模块的 `AGNES_API_KEY` 不会替 AGH 配置账号。

页面先展示本地工具计算，再展示 AGH 实际工具调用。确认第二阶段有真实调用记录、退出成功，才算 Agent 跑通。
模型会收到任务和工具结果，请只使用项目自带仿真数据或你有权发送的数据。

## 5. 可选：直接调用模型生成结构化诊断报告

该模块用来展示独立的 API 客户端、输出校验和上下文管理；它是诊断报告助手，**不替代 AGH Agent 的自主工具执行**。

从安全渠道将 `AGNES_API_KEY` 设置到当前终端环境。可设置 `ZHIWEI_LLM_BASE_URL`、`ZHIWEI_LLM_MODEL`；默认仍为 Agnes。`.env.example` 仅提供变量名，程序不会自动读取 `.env`。

```sh
python -m agent.llm.report --schema
python -m agent.llm.report data/sensor_bearing_wear.csv --output artifacts/llm-report.json
```

实现说明：

- HTTP Bearer 鉴权、30 秒超时；429/指定 5xx/网络错误最多重试 1 次，401 立即失败，错误不输出密钥或响应正文。
- 将 JSON Schema 放入系统提示，再用 Pydantic 严格校验模型返回；四个核心诊断字段另与工具事实比对。失败最多纠正 1 次，仍失败则报错，不返回未经验证的结果。
- 这是客户端 Schema 校验，未声称服务端支持 `strict`/`response_format`。自由文本建议仍可能出错，核心字段校验不等于全文事实证明。
- `fit_context` 先保留系统规则、当前任务和工具事实，预留输出和安全余量，再按完整 user/assistant 轮次删除最旧历史；必需内容超预算时在请求前失败。
- token 数按 UTF-8 字节加开销保守估算，不是供应商 tokenizer 或计费数。CLI 每次独立运行；历史保留策略在 Python 接口与测试中展示。
- 自动测试使用可控模型响应，不代表模型效果评测。真实报告需要有效 Key，且会产生实际 API 请求。

## 6. Docker 与云部署

无密钥镜像：

```sh
docker build -t zhiwei-offline .
docker run --rm -p 8801:8801 zhiwei-offline
```

健康检查：`http://127.0.0.1:8801/api/health` 应返回 `ok=true, mode=offline`。
CI 在 Ubuntu 真正构建此镜像、启动容器并检查 HTTP。只有 Actions 运行成功后，才可将它标记为“已验证”。

完整模型云部署使用 [Render 指南](../deploy/render/README.md)和 `deploy/render/Dockerfile`，在平台 Secret 环境变量中配置 `AGNES_API_KEY`。镜像固定 AGH 提交，可用 `--build-arg AGH_REF=...` 显式升级后重新验证。
该部署需要另行验证 provider/MCP/第二阶段 Agent；离线 Docker 检查不会替它做验证。当前仓库未将其声明为生产服务。
