"""Seed through the legacy SDK and add the offline transfer checks to the verified release context."""
import pathlib
import shutil
import sys

here = pathlib.Path(__file__).resolve().parent
context = pathlib.Path(sys.argv[1])
docker = context / "Dockerfile"
source = docker.read_text()
for old, new in [
    ("COPY seed.mjs snapshot.mjs /opt/lab/", "COPY seed.mjs snapshot.mjs session.mjs /opt/lab/"),
    ("node /opt/lab/seed.mjs && node /opt/lab/snapshot.mjs", "node /opt/lab/seed.mjs && timeout 90s node /opt/lab/session.mjs seed && node /opt/lab/snapshot.mjs"),
    ("run.sh report.mjs /opt/lab/", "run.sh report.mjs session.mjs verify.mjs handoff.sh phone-export.mjs /opt/lab/"),
]:
    if source.count(old) != 1:
        raise ValueError("Unexpected fixture Dockerfile")
    source = source.replace(old, new)
docker.write_text(source)
for name in ["session.mjs", "handoff.sh", "phone-export.mjs"]:
    shutil.copyfile(here / name, context / name)
shutil.copyfile(here.parent / "pid-namespace" / "verify.mjs", context / "verify.mjs")
