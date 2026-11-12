set -euo pipefail
if [[ "$1" == safeguards ]]; then
  exec timeout --kill-after=10s 2m node /opt/lab/safeguards.mjs
fi
set +e
if [[ "$1" == missing ]]; then
  bash /opt/pr-lab/repeat.sh
else
  bash /opt/lab/run.sh "$1"
fi
rc=$?
set -e
if test -f /tmp/orion-custody.jsonl; then
  node --input-type=module - <<'JS'
import fs from 'node:fs';
const counts={};
const examples=[];
for(const l of fs.readFileSync('/tmp/orion-custody.jsonl','utf8').trim().split('\n')) {
  if(!l) continue;
  const e=JSON.parse(l), key=e.kind+'.'+e.event;
  counts[key]=(counts[key]||0)+1;
  if(['issue-refused','outside-backend'].includes(e.event) && examples.length<6) examples.push(e);
}
console.log('CUSTODY '+JSON.stringify({counts,examples}));
JS
fi
exit "$rc"
