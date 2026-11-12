set -euo pipefail
umask 077
test "$(id -u)" -ne 0
test "$OPENCLAW_STATE_DIR" = /home/replay/.openclaw
cli=/opt/beta/node_modules/openclaw/openclaw.mjs
case "$1" in
  prepare)
    mkdir -p "$OPENCLAW_STATE_DIR/workspace"
    printf '%s\n' 'Fictional local identity 7293.' > "$OPENCLAW_STATE_DIR/workspace/IDENTITY.md"
    printf '%s\n' 'Fictional user note 6358.' > "$OPENCLAW_STATE_DIR/workspace/USER.md"
    sha256sum "$OPENCLAW_STATE_DIR"/workspace/{IDENTITY,USER}.md > /handoff/workspace.sha256
    bash /opt/lab/run.sh control
    node /opt/lab/verify.mjs before-transfer
    timeout --kill-after=10s 90s node /opt/lab/session.mjs verify
    sha256sum --check --status /handoff/workspace.sha256
    # All OpenClaw processes have exited. Carry the complete synthetic state directory, including WALs.
    tar -C "$OPENCLAW_STATE_DIR" -cf /handoff/state.tar .
    (cd /handoff && sha256sum state.tar > state.sha256)
    node /opt/lab/phone-export.mjs
    chmod -R a+rX /handoff/phone-v1
    echo 'HANDOFF source=quiescent synthetic-state=archived'
    ;;
  reopen)
    mkdir -p "$OPENCLAW_STATE_DIR"
    (cd /handoff && sha256sum --check --status state.sha256)
    tar -C "$OPENCLAW_STATE_DIR" -xf /handoff/state.tar
    touch /home/replay/.simulate-missing-pid-link
    sha256sum --check --status /handoff/workspace.sha256
    node /opt/lab/verify.mjs restored
    timeout --kill-after=10s 90s node /opt/lab/session.mjs verify
    timeout --kill-after=10s 90s node "$cli" sessions --agent main --json > /tmp/orion-sessions.json
    node --input-type=module - <<'JS'
import assert from 'node:assert/strict';
import fs from 'node:fs';
const report=JSON.parse(fs.readFileSync('/tmp/orion-sessions.json','utf8'));
assert.ok(report.sessions.some(r=>r.key==='agent:main:main' && r.sessionId==='5fd080f7-d376-483d-a065-c212db942f93'));
console.log('SESSIONS cli-listed-original=true');
JS
    node "$cli" gateway run --bind loopback --port 18789 > /tmp/orion-gateway.log 2>&1 &
    gateway=$!
    trap 'kill -TERM "$gateway" 2>/dev/null || true' EXIT
    ready=0
    for _ in $(seq 1 90); do
      kill -0 "$gateway" 2>/dev/null || break
      if curl --noproxy '*' --max-time 2 -fsS http://127.0.0.1:18789/healthz > /tmp/orion-live.json 2>/dev/null; then ready=1; break; fi
      sleep 1
    done
    if [[ "$ready" != 1 ]]; then tail -45 /tmp/orion-gateway.log; exit 1; fi
    node -e "const r=require('/tmp/orion-live.json'); if(r.ok!==true || r.status!=='live') process.exit(1); console.log('GATEWAY loopback-live=true')"
    timeout --kill-after=10s 90s node "$cli" gateway health --json > /tmp/orion-health.json
    node -e "const r=require('/tmp/orion-health.json'); if(r.ok!==true) process.exit(1); console.log('GATEWAY health-rpc=true')"
    kill -TERM "$gateway"
    wait "$gateway" || { rc=$?; [[ "$rc" == 143 ]] || exit "$rc"; }
    trap - EXIT
    node /opt/lab/verify.mjs after-gateway
    timeout --kill-after=10s 90s node /opt/lab/session.mjs verify
    sha256sum --check --status /handoff/workspace.sha256
    node --input-type=module - <<'JS'
import fs from 'node:fs';
import assert from 'node:assert/strict';
const probes=fs.readFileSync('/tmp/orion-replay.jsonl','utf8').trim().split('\n').map(JSON.parse).filter(e=>e.event==='namespace');
assert.ok(probes.length>0 && probes.every(p=>p.readlink==='ENOENT' && p.stat==='ENOENT'));
console.log('HANDOFF target=missing-link pid-probes='+probes.length+' workspace-checksums=ok');
JS
    ;;
  *) exit 2 ;;
esac
