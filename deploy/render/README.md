# 智维 ZHIWEI · 在线体验（Render 免费部署）

在 Render 上以 Docker 方式托管，无需本地开机。

## Render 创建步骤

1. 注册/登录 https://render.com （可直接用 GitHub 账号 `huangfushengxin` 登录，免费，不需要信用卡）
2. 右上 **New +** → **Web Service**
3. 选择 **Public Git repository**，填：
   `https://github.com/huangfushengxin/zhiwei-industrial-agent`
4. 填写：
   | 项 | 值 |
   |---|---|
   | Name | `zhiwei-online` |
   | Language / Runtime | **Docker** |
   | Branch | `main` |
   | **Root Directory** | 留空 |
   | **Dockerfile Path** | `deploy/render/Dockerfile` |
   | Instance Type | **Free** |
5. **Environment Variables** 添加：
   | Key | Value |
   |---|---|
   | `AGNES_API_KEY` | 你的 Agnes 模型 Key（`sk-` 开头） |
6. 点 **Create Web Service**，等待构建（约 10–20 分钟）
7. 构建完成后地址为：`https://<Name>.onrender.com`

## 说明

- 免费实例 512MB 内存；实测 AGH 守护进程 + 工具服务 + 演示服务合计约 130MB，可正常运行。
- 免费实例在 15 分钟无访问后会休眠，**再次打开需等待约 1 分钟冷启动**，属正常现象。
- `AGNES_API_KEY` 只在 Render 的环境变量中保存，不会写入代码或公开仓库。
