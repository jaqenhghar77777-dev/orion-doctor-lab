set -euo pipefail
umask 077
mkdir -p "$OPENCLAW_STATE_DIR/workspace"
printf '%s\n' 'Fictional ARM64 continuity check.' > "$OPENCLAW_STATE_DIR/workspace/IDENTITY.md"
sha256sum "$OPENCLAW_STATE_DIR/workspace/IDENTITY.md" > /tmp/identity.sha256
bash /opt/lab/run.sh missing
node /opt/pr-lab/verify.mjs first
sha256sum --check --status /tmp/identity.sha256
# Reuse the same upgraded directory. The baseline driver would reseed it.
timeout --kill-after=15s 8m node /opt/beta/node_modules/openclaw/openclaw.mjs doctor --fix --non-interactive \
  > /tmp/orion-repeat-output.log 2>&1 || { rc=$?; tail -40 /tmp/orion-repeat-output.log; exit "$rc"; }
node /opt/pr-lab/verify.mjs second
sha256sum --check --status /tmp/identity.sha256
echo 'REPEAT doctorExit=0 synthetic-identity=preserved'
