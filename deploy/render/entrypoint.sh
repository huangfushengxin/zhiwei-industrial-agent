#!/usr/bin/env bash
set -uo pipefail
AGH=/opt/agnes-harness/packages/cli/dist/local/agnes.mjs
export AGNES_PROFILE=local-dev
export ZHIWEI_AGH_HOME=/opt/agnes-harness
export PYTHONIOENCODING=utf-8
PORT="${PORT:-8801}"
log(){ echo "[entrypoint] $*"; }

# 1) 账号与密钥（严格权限：目录 0700 / 文件 0600，AGH 会校验）
mkdir -p /root/.agh/profiles/local-dev /root/.agh/secrets/agnes-ai /root/.agh/skills
chmod 700 /root/.agh /root/.agh/secrets /root/.agh/secrets/agnes-ai
chmod 700 /root/.agh/profiles /root/.agh/profiles/local-dev
if [ -n "${AGNES_API_KEY:-}" ]; then
  printf '{"version":1,"kind":"api-key","provider":"agnes-ai","value":"%s"}' "$AGNES_API_KEY" \
    > /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  chmod 600 /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  log "API Key 已注入（0600）"
else
  log "警告：未设置 AGNES_API_KEY，Agent 将无法调用模型"
fi

# 2) 守护进程放后台（不在关键路径上，避免占用探活时间）
nohup bash -c '
  sleep 2
  node '"$AGH"' daemon start >/tmp/daemon.log 2>&1 || true
  for i in $(seq 1 40); do
    if node '"$AGH"' daemon status 2>/dev/null | grep -q "\"running\":true"; then echo "[daemon] ready"; break; fi
    sleep 5
  done
  if ! node '"$AGH"' mcp list 2>/dev/null | grep -q zhiwei-ops; then
    echo "[daemon] MCP 未注册，补注册"
    /opt/build_setup.sh || true
  fi
  echo "[daemon] setup finished"
' > /tmp/daemon_boot.log 2>&1 &

# 3) 立刻启动演示服务，让平台尽快探活成功
log "启动演示服务 :$PORT"
cd /opt/zhiwei/app
exec python3 demo_server.py --port "$PORT" --host 0.0.0.0
