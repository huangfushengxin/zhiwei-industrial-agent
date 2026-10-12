# 智维 ZHIWEI · AI 工业设备智能运维 Agent

> **让工业设备自己发现故障、制定维修方案、模拟维修，并用数据证明自己修对了。**

| 赛事信息 | |
|---|---|
| 赛事 | 2026 年江苏省 AI+科学与工程创新实践黑客松（高校组） |
| 参赛编号 | **U225** |
| 组别 | **本科生组** |
| 队伍名称 | **SoloAI Lab**（单人队伍） |
| 队长 | **皇甫生昕**（本科生） |
| 参考方向 | 机械工程与数字孪生 · Agent 与 Harness 工程 · 智能制造与系统 |
| 运行底座 | **Agnes Harness (AGH)** |
| 模型 | **Agnes 3.0 Flash（agnes-3.0-flash）** —— 全部模型调用仅使用 Agnes 模型 |

---

## 一、我们解决什么问题

工业现场的旋转设备（泵、风机、电机）运维，长期依赖老师傅经验：**发现异常靠巡检，判断故障靠经验，修完还要再观察一段时间**。常见痛点是：

- 早期劣化发现晚，等到报警时已接近失效；
- 故障判断依赖个人经验，同一现象不同人给出不同结论；
- **修完没有客观验收** —— 修得好不好，只能"感觉"。

**智维要做的，是让 AI 不只"说出哪里坏了"，而是真的调用工具去分析、去修、并用数据证明修好了。**

---

## 二、系统架构

```
                      ┌──────────────────────────────┐
   用户/评委  ───────▶ │  展示层  app/zhiwei-live.html │  交互式诊断演示页面
                      │         app/demo_server.py    │  本地演示服务（SSE 实时推送）
                      └───────────────┬──────────────┘
                                      │ 自然语言任务
                                      ▼
                      ┌──────────────────────────────┐
                      │  Agnes Harness (AGH)  运行底座 │  ← 赛事指定底座
                      │  任务规划 · 工具调用 · 审批 · 记录 │
                      └───────────────┬──────────────┘
                                      │ MCP 协议（stdio）
                                      ▼
                      ┌──────────────────────────────┐
                      │  智维 MCP 工具服务（9 个工具）    │  agent/mcp/
                      └───────────────┬──────────────┘
                                      │
                                      ▼
      ┌───────────────────────────────────────────────────────────┐
      │  工业工具链  tools/                                        │
      │  异常检测 → 故障诊断 → 维修方案 → 模拟维修 → 维修后验证      │
      │  知识库（4 类故障 × 特征指纹 × 维修工序 × 验收标准）           │
      └───────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                            传感器时序数据 data/*.csv
```

**技术要点**

- **AGH 是唯一运行底座**：所有任务的规划、工具调用、执行记录都由 AGH 完成；
- **模型仅限 Agnes**：仅配置 `agnes-ai / agnes-3.0-flash` 一个供应商账号，仓库内不含任何其他厂商模型调用；
- **工具经 MCP 接入**：9 个工具通过 Model Context Protocol（stdio）暴露给 Agent，AGH 侧状态 `connection=ready · tools=9`；
- **只读工具与写盘工具分级**：检测/诊断/方案/验证类工具声明 `readOnlyHint=true` 免审批；写盘类工具（生成维修后数据）走 AGH 审批闸门。

---

## 三、完整闭环（六步）

```
① 数据读取  read_sensor_summary
② 异常检测  detect_anomalies      滚动中位数 + 鲁棒 z 分数（中位数/MAD）
③ 故障诊断  diagnose_fault        特征指纹余弦匹配 + 维修建议
④ 维修方案  plan_repair            停机策略/工时/安全措施/分步工序/备件/验收标准
⑤ 模拟维修  simulate_repair        按修复彻底度生成维修后复测数据
⑥ 维修后验证 verify_repair         以【维修前基线】对比，判定 success/partial/failed
        └── 未通过 → 重新规划 → 再次维修 → 再次验证（最多 3 次）
```

**两个关键工程决策**

1. **跨基线验证**：维修后数据若"从第一秒就带着残留故障"，用它自己的前段做基线会把残留当成正常而漏判。因此验证一律以**维修前的健康基线**为参照。
2. **可信的失败**：验证不通过时系统**不会假装修好**，而是给出残留测点、残留幅度（σ）和残留故障候选，触发重新规划。

---

## 四、快速开始（复现步骤）

### 4.1 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Node.js | ≥ 24.10 | 运行 AGH |
| pnpm | 10.34.5 | AGH 锁定版本（用 corepack 激活） |
| Python | 3.11+ | 运行工具链与演示服务（**仅标准库 + mcp SDK**） |
| Agnes API Key | — | 需自行申请；配置进 AGH，**不要写进代码仓库** |

### 4.2 搭建 AGH（约 15 分钟）

```bash
git clone https://github.com/AgnesAI-Labs/agnes-harness.git
cd agnes-harness
corepack prepare pnpm@10.34.5 --activate
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @agnes/cli build:local
node packages/cli/dist/local/agnes.mjs serve --port 4180 --profile local-dev
```

> Windows 需要 Visual Studio C++ 生成工具（编译原生模块），详见 AGH 官方安装文档。

### 4.3 配置 Agnes 模型

```bash
node packages/cli/dist/local/agnes.mjs config
# Provider 选 Agnes AI（Base URL: https://api.agnes-ai.cn/v1）
# 粘贴你的 Agnes API Key，选择 agnes-3.0-flash
```

### 4.4 接入智维工具（MCP）

```bash
node packages/cli/dist/local/agnes.mjs mcp add zhiwei-ops --name "智维工业运维工具" \
  --stdio <python.exe> --arg <项目路径>\agent\mcp\zhiwei_mcp_server.py \
  --allow-tool list_scenarios --allow-tool read_sensor_summary --allow-tool detect_anomalies \
  --allow-tool diagnose_fault --allow-tool analyze_equipment --allow-tool plan_repair \
  --allow-tool simulate_repair --allow-tool verify_repair --allow-tool run_closed_loop
# 然后 trust → enable（详见 AGH MCP 文档）
```

### 4.5 一键复现全部验收

```powershell
.\run_all.ps1
```

会依次执行：故障诊断验收（5/5）→ 闭环验收（6/6）→ 异常恢复验收（4/4）→ 三案例演示（3/3）→ 生成展示页。

### 4.6 打开演示

```powershell
cd app
.\start_demo.ps1          # 启动本地演示服务
# 浏览器打开 http://127.0.0.1:8801/
```

演示页支持：选择设备（M-001~M-005）/ 上传 CSV / 选择「维修前基线」→ 点「开始智能诊断」，
页面实时显示 **Agent 执行时间线**、故障诊断、再次维修方案与维修验证结果。

**离线查看**：`app/zhiwei-demo.html` 是**自包含单文件**（数据内嵌），双击即可查看三案例结果，无需任何环境。

---

## 五、目录结构

```
AI-Industrial-Agent/
├─ README.md                      本文件
├─ run_all.ps1                    一键复现全部验收
├─ package_submission.ps1         生成符合官方命名规则的提交 ZIP
├─ docs/
│   ├─ 作品信息.md                 提交表单填写内容（含 ≤50 字简介）
│   ├─ 成员分工与独立完成声明.md     官方必填
│   └─ 第三方素材来源说明.md        官方必填（如实说明）
├─ app/                           展示层
│   ├─ zhiwei-live.html           交互式在线诊断页（真跑 AGH Agent）
│   ├─ demo_server.py             本地演示服务（SSE 实时推送）
│   ├─ zhiwei-demo.html           三案例结果展示页（自包含，可离线/上云）
│   └─ start_demo.ps1             一键启动
├─ agent/mcp/                     智维 MCP 工具服务（9 个工具）
├─ tools/                         工业工具链
│   ├─ fault_library.py           故障知识库（特征 + 维修方案）
│   ├─ anomaly_detect.py          异常检测
│   ├─ fault_diagnose.py          故障诊断
│   ├─ repair_plan.py             维修方案生成
│   ├─ simulate_repair.py         模拟维修
│   ├─ verify_repair.py           维修后验证
│   ├─ closed_loop.py             闭环编排
│   ├─ demo_misdiagnosis.py       错误诊断与恢复演示
│   ├─ validate_*.py              各阶段验收脚本
│   └─ make_test_csvs.py          测试数据生成
├─ data/                          传感器数据
│   ├─ sensor_*.csv               5 类工况数据
│   ├─ test/                      三份测试 CSV（正常/故障/维修失败）
│   └─ repairs/                   维修后复测数据与闭环记录
└─ evidence/                      运行与验证证据（Day1–Day5）
    ├─ day1/ … day5/              AGH 会话导出、trace、验收报告
    └─ hackathon-notice.txt       赛事通知文本（便于对照）
```

---

## 六、验证结果（可复现）

| 验收项 | 结果 | 脚本 |
|---|---|---|
| 故障诊断准确率 | **5/5 = 100%** | `tools/validate_pipeline.py` |
| 完整闭环（含失败重规划） | **6/6 = 100%** | `tools/validate_closed_loop.py` |
| 异常恢复（错误诊断→纠正） | **4/4 = 100%** | `tools/validate_day4.py` |
| 三测试案例（正常/边界/失败） | **3/3 = 100%** | `tools/run_demo_cases.py` |
| MCP 工具可用性 | **9/9 可调用** | `agent/mcp/verify_mcp_client.py` |

**运行证据**（`evidence/`）：每个阶段的 AGH 会话导出（HTML + JSON）、闭环 trace、
验收报告 JSON，可作为"Agnes 模型参与核心任务"的调用链证据。

---

## 七、第三方素材来源

详见 [`docs/第三方素材来源说明.md`](docs/第三方素材来源说明.md)。核心说明：

- **Agnes Harness (AGH)**：Apache-2.0，来自 `github.com/AgnesAI-Labs/agnes-harness`，作为智能体运行底座（未修改源码）；
- **Agnes 模型**：`agnes-3.0-flash`，经官方 API 调用；
- **MCP Python SDK**：`mcp` 2.3.0（MIT），用于把工具暴露给 AGH；
- **其余全部为团队原创代码**，Python 侧除 MCP SDK 外仅使用标准库；
- **数据**：全部由本项目的生成器程序化生成（仿真数据），未使用任何第三方数据集。

---

## 八、许可

本项目原创代码采用 **Apache-2.0** 许可。AGH 及其派生部分遵循其原始许可（Apache-2.0）。