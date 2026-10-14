#!/usr/bin/env bash
set -uo pipefail
AGH=/opt/agnes-harness/packages/cli/dist/local/agnes.mjs
export AGNES_PROFILE=local-dev
export ZHIWEI_AGH_HOME=/opt/agnes-harness
export PYTHONIOENCODING=utf-8
PORT="${PORT:-8801}"
log(){ echo "[entrypoint] $*"; }

# 0) 清掉构建期遗留的守护进程状态：构建时还没有 API Key，
#    那份状态会把账号记成“无凭据”，必须在运行时重新生成。
rm -rf /root/.agh/data /root/.agh/cache

# 1) 写入账号与密钥（目录 0700 / 文件 0600，AGH 会严格校验）
mkdir -p /root/.agh/profiles/local-dev /root/.agh/secrets/agnes-ai /root/.agh/skills
chmod 700 /root/.agh /root/.agh/secrets /root/.agh/secrets/agnes-ai /root/.agh/profiles /root/.agh/profiles/local-dev
printf 'approvals:\n  mode: off\n' > /root/.agh/profiles/local-dev/profile.yaml
cat > /root/.agh/profiles/local-dev/configuration.json <<'JSON'
{"version":2,"profile":"local-dev","revision":1,"accounts":[{"accountId":"acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef","label":"agnes-hackathon","id":"agnes-ai","route":"account-acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef","baseUrl":"https://api.agnes-ai.cn/v1","model":"agnes-3.0-flash","models":[{"id":"agnes-3.0-flash","name":"Agnes 3.0 Flash","reasoning":false,"contextWindow":200000}],"credentialRef":"secret://agnes-ai/account-127a019d74b0b9eef2e1766b-r1","enabled":true,"authType":"api-key"}],"defaultAccountId":"acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef"}
JSON
if [ -n "${AGNES_API_KEY:-}" ]; then
  printf '{"version":1,"kind":"api-key","provider":"agnes-ai","value":"%s"}' "$AGNES_API_KEY" \
    > /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  chmod 600 /root/.agh/secrets/agnes-ai/account-127a019d74b0b9eef2e1766b-r1
  log "API Key 已注入（0600）"
else
  log "警告：未设置 AGNES_API_KEY，Agent 将无法调用模型"
fi

# 2) 后台：守护进程 + MCP 注册（不在关键路径上，避免占用平台探活时间）
nohup bash -c '
  set -x
  sleep 2
  echo "===== .agh 状态 ====="
  ls -la /root/.agh /root/.agh/secrets/agnes-ai || true
  echo "===== 启动守护进程 ====="
  node '"$AGH"' daemon start
  echo "daemon start rc=$?"
  for i in $(seq 1 40); do
    if node '"$AGH"' daemon status 2>/dev/null | grep -q "\"running\":true"; then echo "[daemon] ready"; break; fi
    sleep 5
  done
  echo "===== 守护进程状态 ====="
  node '"$AGH"' daemon status || true
  echo "===== 模型连通性自检 ====="
  node '"$AGH"' doctor provider --probe --json || true
  echo "===== daemon.log ====="
  tail -60 /tmp/daemon.log 2>/dev/null || true
  echo "===== 注册 MCP ====="
  if ! node '"$AGH"' mcp list 2>/dev/null | grep -q zhiwei-ops; then
    /opt/build_setup.sh || true
  fi
  echo "===== MCP 列表 ====="
  node '"$AGH"' mcp list || true
  echo "[daemon] setup finished"
' > /tmp/daemon_boot.log 2>&1 &
# 把后台日志同时镜像到容器 stdout，便于在平台日志里查看
( sleep 5; tail -n +1 -f /tmp/daemon_boot.log & ) >/dev/null 2>&1 &

# 3) 立刻启动演示服务，让平台尽快探活成功
log "启动演示服务 :$PORT"
cd /opt/zhiwei/app
exec python3 demo_server.py --port "$PORT" --host 0.0.0.0
