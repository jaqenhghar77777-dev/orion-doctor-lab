#!/usr/bin/env bash
# Run on the phone. The commit argument pins both the initial branch check and the server-side gate.
set -euo pipefail
umask 077
repo=jaqenhghar77777-dev/orion-doctor-lab
commit=${1:?expected reviewed commit}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
test "$(gh api "repos/$repo/branches/main" --jq .commit.sha)" = "$commit"
evidence=$(mktemp -d /root/orion-rehearsal-receipt-XXXXXXXX)
printf 'Private report and artifact key directory: %s\n' "$evidence"
gh run download 43225579792 --repo "$repo" --name orion_real_state_rehearsal_v1_primary --dir "$evidence/primary"
(
  cd "$evidence/primary"
  printf '%s  %s\n' bfc0eb39854cdbb1ca7c47ebcf5cb97d3ea27e3d3c3c8e2bd2f0c3d91cf94ae9 migration-report.json | sha256sum -c -
)
# Never replace an existing download key on an accidental second invocation.
secret=ORION_HANDOFF_20261112_V2
names=$(gh secret list --repo "$repo" --json name --jq '.[].name')
if grep -Fxq "$secret" <<< "$names"; then
  echo 'STOP: handoff key already registered. Keep the first receipt directory and check Actions.'
  exit 1
fi
python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_hex(32))' > "$evidence/handoff.key"
gh secret set "$secret" --repo "$repo" < "$evidence/handoff.key"
gh workflow run orion-real-state-rehearsal.yml --repo "$repo" --ref main \
  -f release_tag=orion-rehearsal-input-20261112-v1 -f attempt=corrective \
  -f "reviewed_change_commit=$commit"
printf 'DISPATCH_ACCEPTED\nKeep %s private for the DSHBox handoff.\n' "$evidence"
