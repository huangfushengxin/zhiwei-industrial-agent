#!/usr/bin/env bash
set -uo pipefail
AGH=/opt/agnes-harness/packages/cli/dist/local/agnes.mjs
export AGNES_PROFILE=local-dev
export ZHIWEI_AGH_HOME=/opt/agnes-harness
export PYTHONIOENCODING=utf-8
PORT="${PORT:-8801}"
DIAG=/opt/zhiwei/app/diag.txt
log(){ echo "[entrypoint] $*"; }

# 0) 清掉构建期遗留的守护进程运行状态（构建时还没有 API Key）
rm -rf /root/.agh/data /root/.agh/cache

# 1) 注入密钥（目录 0700 / 文件 0600，AGH 会严格校验）
mkdir -p /root/.agh/secrets/agnes-ai
chmod 700 /root/.agh /root/.agh/secrets /root/.agh/secrets/agnes-ai || true
if [ -n "${AGNES_API_KEY:-}" ]; then
  printf '{"version":1,"kind":"api-key","provider":"agnes-ai","value":"%s"}' "$AGNES_API_KEY" \
    > /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  chmod 600 /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  log "API Key 已注入（0600）"
else
  log "警告：未设置 AGNES_API_KEY"
fi

# 2) 后台：守护进程 + 自检 + MCP 注册；诊断写入 /opt/zhiwei/app/diag.txt（可通过 /diag.txt 查看）
nohup bash -c '
  exec > '"$DIAG"' 2>&1
  set -x
  echo "=== 时间: $(date -u) ==="
  echo "=== /root/.agh ==="; ls -la /root/.agh; ls -la /root/.agh/profiles/local-dev; ls -la /root/.agh/secrets/agnes-ai
  echo "=== configuration.json ==="; cat /root/.agh/profiles/local-dev/configuration.json
  echo "=== daemon start ==="; node '"$AGH"' daemon start; echo "rc=$?"
  for i in $(seq 1 40); do
    if node '"$AGH"' daemon status 2>/dev/null | grep -q "\"running\":true"; then echo "daemon ready"; break; fi
    sleep 5
  done
  echo "=== daemon status ==="; node '"$AGH"' daemon status
  echo "=== doctor provider --probe ==="; node '"$AGH"' doctor provider --probe --json
  echo "=== mcp list ==="; node '"$AGH"' mcp list
  if ! node '"$AGH"' mcp list 2>/dev/null | grep -q zhiwei-ops; then
    echo "=== 注册 MCP ==="; /opt/build_setup.sh || true
    echo "=== mcp list (after) ==="; node '"$AGH"' mcp list
  fi
  echo "=== /tmp/daemon.log ==="; tail -80 /tmp/daemon.log 2>/dev/null
  echo "=== setup finished ==="
' >/dev/null 2>&1 &

# 3) 前台：演示服务
log "启动演示服务 :$PORT"
cd /opt/zhiwei/app
exec python3 demo_server.py --port "$PORT" --host 0.0.0.0
