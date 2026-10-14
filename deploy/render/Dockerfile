# 智维 ZHIWEI · 在线体验（Render 免费实例）
# 构建上下文 = 仓库根目录；Dockerfile 路径 = deploy/render/Dockerfile
FROM node:24-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    AGNES_PROFILE=local-dev \
    ZHIWEI_AGH_HOME=/opt/agnes-harness

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates build-essential python3 python3-pip python3-venv \
      bubblewrap util-linux procps \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare pnpm@10.34.5 --activate

# ---------- 1) 构建 Agnes Harness（官方源码） ----------
RUN git clone --depth 1 https://github.com/AgnesAI-Labs/agnes-harness /opt/agnes-harness
WORKDIR /opt/agnes-harness
RUN pnpm config set registry https://registry.npmmirror.com \
 && pnpm install --frozen-lockfile \
 && pnpm --filter @agnes/cli build:local \
 && test -f packages/cli/dist/local/agnes.mjs \
 && echo "AGH build OK"

# ---------- 2) 智维项目 ----------
WORKDIR /opt/zhiwei
COPY app   /opt/zhiwei/app
COPY agent /opt/zhiwei/agent
COPY tools /opt/zhiwei/tools
COPY data  /opt/zhiwei/data
RUN python3 -m pip install --break-system-packages --no-cache-dir \
      -i https://pypi.tuna.tsinghua.edu.cn/simple "mcp==2.3.0" \
 && python3 -c "import mcp, sys; print('mcp SDK OK', sys.version)"

# ---------- 3) AGH Skill ----------
COPY deploy/render/bootstrap /opt/bootstrap
RUN mkdir -p /root/.agh/skills && cp -r /opt/bootstrap/skills/. /root/.agh/skills/ && ls -R /root/.agh/skills

# ---------- 4) 构建期注册 MCP 工具（trusted + enabled） ----------
COPY deploy/render/build_setup.sh /opt/build_setup.sh
RUN chmod +x /opt/build_setup.sh && /opt/build_setup.sh || echo "WARN: build_setup 未成功，运行时将重试"

# ---------- 5) 运行时 ----------
COPY deploy/render/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh
EXPOSE 8801
CMD ["/opt/entrypoint.sh"]
