"""Retarget the original fixture and diagnostic instrumentation to the published beta.2."""
import pathlib
import re
import sys

destination = pathlib.Path(sys.argv[1])
sha1 = sys.argv[2].strip()
if not re.fullmatch(r"[0-9a-f]{40}", sha1):
    raise ValueError("Expected the version-specific npm shasum")


def substitute(source, old, new, count):
    if source.count(old) != count:
        raise ValueError(f"Unexpected count for {old!r}")
    return source.replace(old, new)


docker = destination / "Dockerfile"
source = substitute(docker.read_text(), "2026.11.5-beta.1", "2026.11.5-beta.2", 4)
source = substitute(source, "cc6d3b105b938acaf9301f17daa3985acd29fce0", sha1, 1)
docker.write_text(source)
instrument = destination / "instrument.cjs"
source = substitute(instrument.read_text(), "2026.11.5-beta.1", "2026.11.5-beta.2", 1)
# Build hashes change between releases. Keep the original guard and CLI-boundary checks.
specific_bundle = "'gateway-state-owner-DQ8gMS4R.mjs'"
source = substitute(source, specific_bundle, "[...guardBundles].find(b => /^gateway-state-owner-[^/]+\\.mjs$/.test(b))", 1)
instrument.write_text(source)
