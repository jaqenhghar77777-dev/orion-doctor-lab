"""Reuse the verified ARM64 runtime/package recipe without fixture data or instrumentation."""
from pathlib import Path
import shutil
import sys

context = Path(sys.argv[1])
source = (context / "Dockerfile").read_text()
runtime, remainder = source.split("FROM runtime AS legacy\n", 1)
legacy, final = remainder.split("\nFROM runtime\n", 1)
for line in [
    "COPY instrument.cjs probe-helpers.js run.sh report.mjs /opt/lab/\n",
    "RUN --network=none NODE_PATH=/opt/trace/node_modules node /opt/lab/instrument.cjs\n",
    'ENTRYPOINT ["/bin/bash", "/opt/lab/run.sh"]\n',
]:
    if final.count(line) != 1:
        raise ValueError("Unexpected pinned Dockerfile")
    final = final.replace(line, "")
final = final.replace("USER replay\n", "COPY compat.mjs verify.mjs reopen.mjs run.py schema-only.mjs schema-selftest.py /opt/real-lab/\nUSER replay\n")
final += 'ENTRYPOINT ["python3", "/opt/real-lab/run.py"]\n'
here = Path(__file__).resolve().parent
legacy = legacy.replace('COPY seed.mjs snapshot.mjs /opt/lab/', 'COPY seed.mjs snapshot.mjs session.mjs schema-fixture.mjs /opt/lab/')
legacy = legacy.replace('node /opt/lab/seed.mjs && node /opt/lab/snapshot.mjs',
    'node /opt/lab/seed.mjs && timeout 90s node /opt/lab/session.mjs seed && node /opt/lab/schema-fixture.mjs && node /opt/lab/snapshot.mjs')
snapshot = context / 'snapshot.mjs'
original = "['state/openclaw.sqlite', 'agents/main/agent/openclaw-agent.sqlite']"
if snapshot.read_text().count(original) != 1:
    raise ValueError('Unexpected fixture snapshot source')
snapshot.write_text(snapshot.read_text().replace(original,
    "['state/openclaw.sqlite', 'agents/main/agent/openclaw-agent.sqlite', 'agents/openclaw/agent/openclaw-agent.sqlite']"))
(context / "Dockerfile").write_text(runtime + 'FROM runtime AS legacy\n' + legacy + "\nFROM runtime\n" + final)
shutil.copyfile(here.parent / 'offline-copy/session.mjs', context / 'session.mjs')
for name in ("verify.mjs", "reopen.mjs", "run.py", "schema-only.mjs", "schema-selftest.py", "schema-fixture.mjs"):
    shutil.copyfile(here / name, context / name)
# Use exactly the candidate's canonical fingerprint algorithm.
compat = here.parent / "real-state-preparation/export_candidate_v2.mjs"
(context / "compat.mjs").write_text(compat.read_text() + "\nexport { tables, rows, fingerprint, fingerprintRows, logicalEvent };\n")
