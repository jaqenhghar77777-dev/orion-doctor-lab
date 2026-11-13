"""Exercise beta.1's shipped live-input reader on one fictional database."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PACKAGE = Path("/root/orion-dshbox-chat-v1/runtime-2026.11.5-beta.1/package")
VERSION = "2026.11.5-beta.1"
FUNCTION = "prepareForeignLiveSessionPendingInputEntries"

DRIVER = r"""
import fs from 'node:fs';
import path from 'node:path';
import { registerHooks } from 'node:module';
import { DatabaseSync } from 'node:sqlite';
import { pathToFileURL, fileURLToPath } from 'node:url';

const [chunk, expectedPlatform, expectedVersion] = process.argv.slice(2);
const out = {result:'PROBE_STOP', stage:'node'};
const emit = () => fs.writeFileSync(1, JSON.stringify(out) + '\n');
try {
  if (process.platform+'/'+process.arch !== expectedPlatform || process.version !== expectedVersion)
    throw Error('unexpected Node');
  const state = process.env.OPENCLAW_STATE_DIR;
  const agent = path.join(state, 'agents/main');
  const dbFile = path.join(agent, 'agent/openclaw-agent.sqlite');
  fs.mkdirSync(path.dirname(dbFile), {recursive:true});
  fs.mkdirSync(path.join(agent,'sessions'), {recursive:true});
  out.stage = 'fictional-sqlite';
  const db = new DatabaseSync(dbFile);
  try {
    db.exec('CREATE TABLE fictional(value INTEGER)');
    const native = db.location();
    const expected = fs.statSync(dbFile, {bigint:true});
    out.sqlite_path_equals_requested = native === dbFile;
    out.sqlite_path_equals_node_realpath = native === fs.realpathSync.native(dbFile);
    const observed = fs.statSync(native, {bigint:true,throwIfNoEntry:false});
    out.sqlite_path_same_file = !!observed && observed.dev === expected.dev && observed.ino === expected.ino;
  } finally { db.close(); }

  // Expose the original bundled function only in this disposable Node process.
  // Its body, imported dependencies and every ownership check run unchanged.
  out.stage = 'load-shipped-reader';
  const url = pathToFileURL(chunk).href;
  registerHooks({load(specifier, context, next) {
    const result = next(specifier, context);
    if (specifier !== url) return result;
    return {...result, source:Buffer.from(result.source).toString('utf8') +
      '\nexport { prepareForeignLiveSessionPendingInputEntries as orionLabRead };\n'};
  }});
  const {orionLabRead} = await import(url);
  out.stage = 'stock-live-input-read';
  const input = {agentId:'main', sessionId:'fictional-id', sessionKey:'agent:main:fictional',
                 storePath:path.join(agent,'sessions/sessions.json')};
  const read = await orionLabRead(input);
  if (read().size !== 0) throw Error('unexpected inputs');
  out.result = 'ISOLATED_READ_PASS';
} catch (err) {
  if (err.message === 'Live input changed its captured database owner') {
    out.result = 'ISOLATED_OWNER_REFUSAL';
    // Source positions refer to the unmodified guard in the installed bundle.
    const frame = String(err.stack).match(/(file:\/\/[^\s()]+?\.m?js):(\d+):(\d+)/);
    if (frame) {
      const target = fileURLToPath(frame[1]);
      out.frame = path.basename(target)+':'+frame[2]+':'+frame[3];
      const lines = fs.readFileSync(target,'utf8').split('\n');
      const ending = Number(frame[2]);
      const line = lines.slice(Math.max(0, ending-2), ending).join(' ');
      // Use the adjoining condition only when it unambiguously leads to this throw.
      if (/if\s*\(\s*!identity\s*\)\s*\{?\s*throw new Error/.test(line)) out.branch='missing candidate identity';
      if (/if\s*\(options\.path\s*!==\s*prepared\.canonicalPath\)\s*\{?\s*throw new Error/.test(line))
        out.branch='prepared path differs';
    }
  } else {
    out.error_type = err.name;
    if (/^[A-Z][A-Z0-9_]{1,60}$/.test(err.code||'')) out.error_code=err.code;
  }
}
emit();
process.exit(out.result==='ISOLATED_READ_PASS'?0:1);
"""


def find_reader(dist):
    # Search executable JavaScript only. Skip dependency trees and symlinks.
    marker = ("async function " + FUNCTION + "(").encode()
    for directory, subdirs, files in os.walk(dist):
        subdirs[:] = sorted(d for d in subdirs if d != "node_modules" and not (Path(directory)/d).is_symlink())
        for name in sorted(files):
            if name.endswith((".js", ".mjs")):
                f = Path(directory) / name
                if not f.is_symlink() and f.is_file() and marker in f.read_bytes():
                    return f
    raise ValueError("named stock reader unavailable in dist")


def main():
    os.umask(0o077)
    meta = json.loads((PACKAGE / "package.json").read_bytes())
    if meta.get("name") != "openclaw" or meta.get("version") != VERSION:
        raise ValueError("unexpected persistent runtime")
    node = shutil.which("node")
    if not node:
        raise ValueError("Node unavailable")
    with tempfile.TemporaryDirectory(prefix="orion-fictional-input-", dir="/root") as tmp:
        base = Path(tmp)
        state = base / "home/.openclaw"
        workspace = state / "workspace"
        workspace.mkdir(parents=True)
        config = state / "openclaw.json"
        config.write_text(json.dumps({"channels":{}, "plugins":{"enabled":False},
                                     "agents":{"defaults":{"workspace":str(workspace)}}}))
        env = {"HOME":str(state.parent), "OPENCLAW_HOME":str(state.parent),
               "OPENCLAW_STATE_DIR":str(state), "OPENCLAW_CONFIG_PATH":str(config),
               "OPENCLAW_WORKSPACE_DIR":str(workspace), "OPENCLAW_SKIP_CHANNELS":"1",
               "OPENCLAW_DISABLE_BONJOUR":"1", "NODE_DISABLE_COMPILE_CACHE":"1",
               "PATH":str(Path(node).parent)+":/usr/bin:/bin", "LANG":"C.UTF-8"}
        for k in ("TMPDIR","XDG_RUNTIME_DIR","XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","XDG_STATE_HOME"):
            directory = base/k.lower()
            directory.mkdir()
            env[k] = str(directory)
        driver = base / "probe.mjs"
        driver.write_text(DRIVER)
        chunk = find_reader(PACKAGE / "dist")
        proc = subprocess.run(["/usr/bin/timeout","--kill-after=5s","90",node,"--no-warnings",
                               str(driver),str(chunk),"linux/arm64","v24.19.0"],
                              env=env,cwd=workspace,capture_output=True,timeout=105)
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(b'{"result":'):
                report = json.loads(line)
                print(json.dumps(report, indent=2))
                return proc.returncode
        print("PROBE_STOP — no diagnostic receipt; child exit", proc.returncode)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        sys.exit("PROBE_STOP — " + str(e))
