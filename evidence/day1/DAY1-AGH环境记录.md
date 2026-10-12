# Day 1 记录 —— AGH 环境（智维 · AI 工业设备智能运维 Agent）

生成时间：2026-10-08

## 1. 环境

| 项目 | 版本/位置 |
|---|---|
| Node.js | v24.19.0（要求 >= 24.10） |
| pnpm | 10.34.5（由 corepack 锁定，仓库 packageManager 指定） |
| Git | git version 2.53.0.windows.3 |
| C++ 编译器 | Visual Studio 2022 Build Tools + Windows SDK 10.0.26100 |
| Node 头文件 | %LOCALAPPDATA%\node-gyp\Cache\24.19.0 |
| AGH 源码 | C:\Users\<user>\Documents\ChatGPT\SoloAI-Lab\agnes-harness |
| AGH commit | cde816b88c737b9fd04e7ef55b899e7b4cd55eb7 |
| AGH 数据目录 | C:\Users\<user>\.agh |

## 2. 构建与启动

```
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @agnes/cli build:local
node packages/cli/dist/local/agnes.mjs serve --port 4180 --profile local-dev
```

Web 工作台：http://127.0.0.1:4180/

## 3. 模型配置

- Provider：Agnes AI（agnes-ai）
- Base URL：https://api.agnes-ai.cn/v1
- 模型：agnes-3.0-flash（网关返回的唯一可用模型）
- 说明：仅接入 Agnes 模型，符合赛事"只允许 Agnes 模型"的要求
- API Key 保存在本地后端，不落库明文回报

## 4. 第一个 Agent 任务

会话 ID：agnes:local:local-dev:cli:workspace:aadac60696a969f0

提示词：

> 只读浏览当前项目，用中文简要说明主要目录及用途，不要修改文件，不要运行安装命令。

结果：Agent 自主调用 `ls`、`read` 工具读取项目后，用中文输出了完整的目录结构说明（工具调用链可在导出的记录中查看）。

## 5. 产出文件

- agh-day1-first-agent.html —— 人类可读的执行记录
- agh-day1-first-agent.json —— 原始会话数据（含完整工具调用链）

## 6. 备注

- AGH 在 Windows 上需要 C++ 生成工具编译原生模块，已安装。
- AGH 由独立 PowerShell 窗口承载，关闭该窗口服务即停止。
