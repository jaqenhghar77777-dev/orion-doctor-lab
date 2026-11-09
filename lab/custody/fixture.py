"""Extract the seven fixture files embedded in the independently verified baseline."""
import hashlib
import pathlib
import sys

workflow, destination = map(pathlib.Path, sys.argv[1:])
content = workflow.read_bytes()
expected = "a8b42abdb4f7607546b77cdf85515078846efee4676e33453d2bae5204de5ccc"
if hashlib.sha256(content).hexdigest() != expected:
    raise SystemExit("Baseline workflow differs from lab run 1")
destination.mkdir(parents=True, exist_ok=True)
lines = [s[10:] if s.startswith(" " * 10) else s for s in content.decode().splitlines()]
for name in ["Dockerfile", "seed.mjs", "snapshot.mjs", "probe-helpers.js", "instrument.cjs", "run.sh", "report.mjs"]:
    start = lines.index("cat > " + name + " <<'ORION_END_FILE'") + 1
    end = lines.index("ORION_END_FILE", start)
    (destination / name).write_text("\n".join(lines[start:end]) + "\n")
