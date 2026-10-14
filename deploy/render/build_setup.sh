#!/usr/bin/env bash
# 构建期：启动守护进程并把智维 MCP 工具注册成 trusted+enabled
set -uo pipefail
AGH=/opt/agnes-harness/packages/cli/dist/local/agnes.mjs
export AGNES_PROFILE=local-dev

mkdir -p /root/.agh/profiles/local-dev
printf 'approvals:\n  mode: off\n' > /root/.agh/profiles/local-dev/profile.yaml
cat > /root/.agh/profiles/local-dev/configuration.json <<'JSON'
{"version":2,"profile":"local-dev","revision":1,"accounts":[{"accountId":"acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef","label":"agnes-hackathon","id":"agnes-ai","route":"account-acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef","baseUrl":"https://api.agnes-ai.cn/v1","model":"agnes-3.0-flash","models":[{"id":"agnes-3.0-flash","name":"Agnes 3.0 Flash","reasoning":false,"contextWindow":200000}],"credentialRef":"secret://agnes-ai/account-127a019d74b0b9eef2e1766b-r1","enabled":true,"authType":"api-key"}],"defaultAccountId":"acct-5af84583-b38f-4ae7-84aa-fdb1b7a566ef"}
JSON

echo "== daemon start =="
node "$AGH" daemon start >/tmp/d.log 2>&1 || true
for i in $(seq 1 24); do
  if node "$AGH" daemon status 2>/dev/null | grep -q '"running":true'; then echo "daemon ready"; break; fi
  sleep 5
done
node "$AGH" daemon status || true

echo "== mcp add =="
CMDS="node $AGH mcp add zhiwei-ops --profile local-dev --name zhiwei-ops --stdio /usr/bin/python3 --arg /opt/zhiwei/agent/mcp/zhiwei_mcp_server.py"
for t in list_scenarios read_sensor_summary detect_anomalies diagnose_fault analyze_equipment plan_repair simulate_repair verify_repair run_closed_loop; do
  CMDS="$CMDS --allow-tool $t"
done
printf 'y\n' | script -qec "$CMDS" /dev/null 2>&1 | tee /tmp/mcp_add.log || true

REV=$(grep -oE 'revision=[0-9a-f]{64}' /tmp/mcp_add.log | head -1 | cut -d= -f2)
echo "captured revision: ${REV:-<none>}"

if [ -n "${REV:-}" ]; then
  echo "== mcp trust =="
  printf 'y\n' | script -qec "node $AGH mcp trust zhiwei-ops --expected-revision $REV" /dev/null 2>&1 | tail -5 || true
  echo "== mcp enable =="
  printf 'y\n' | script -qec "node $AGH mcp enable zhiwei-ops --expected-revision $REV" /dev/null 2>&1 | tail -5 || true
fi
node "$AGH" mcp list || true
