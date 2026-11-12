"""Reuse the verified ARM64 runtime/package recipe without fixture data or instrumentation."""
from pathlib import Path
import shutil
import sys

context = Path(sys.argv[1])
source = (context / "Dockerfile").read_text()
runtime, remainder = source.split("FROM runtime AS legacy\n", 1)
_, final = remainder.split("\nFROM runtime\n", 1)
for line in [
    "COPY --from=legacy --chown=replay:replay /fixture/ /fixture/\n",
    "COPY instrument.cjs probe-helpers.js run.sh report.mjs /opt/lab/\n",
    "RUN --network=none NODE_PATH=/opt/trace/node_modules node /opt/lab/instrument.cjs\n",
    'ENTRYPOINT ["/bin/bash", "/opt/lab/run.sh"]\n',
]:
    if final.count(line) != 1:
        raise ValueError("Unexpected pinned Dockerfile")
    final = final.replace(line, "")
files = ("snapshot.mjs", "verify.mjs", "usability.mjs", "usability.py", "run.py")
final = final.replace("USER replay\n", "COPY compat.mjs " + " ".join(files) + " /opt/real-lab/\nUSER replay\n")
final += 'ENTRYPOINT ["python3", "/opt/real-lab/run.py"]\n'
here = Path(__file__).resolve().parent
(context / "Dockerfile").write_text(runtime + "FROM runtime\n" + final)
for name in files:
    shutil.copyfile(here / name, context / name)
# Use exactly the candidate's canonical fingerprint algorithm.
compat = here.parent / "real-state-preparation/export_candidate_v2.mjs"
(context / "compat.mjs").write_text(compat.read_text() + "\nexport { tables, rows, fingerprint, fingerprintRows, logicalEvent };\n")
