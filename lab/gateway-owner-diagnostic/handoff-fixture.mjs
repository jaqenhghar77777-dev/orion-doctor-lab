// Test-only producer inputs for one fictional first-message attempt.
// No guard, receipt, agent identity or selection assertion is synthesized here.
import fs from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
const db = '/home/replay/.openclaw/agents/main/agent/openclaw-agent.sqlite';
const family = '/home/replay/fixture';
const sibling = family + '.late.sqlite';
const alias = '/home/replay/fixture-alias.sqlite';
export const mode = process.env.ORION_HANDOFF_CASE;
const prepared = new Set(['prepared','alias','other-file','revoked','stable-handoff']);
export function captureInput(scope) {
  if (prepared.has(mode)) return {...scope,storePath:db};
  if (mode === 'late-sibling') return {...scope,storePath:family+'.json'};
  return scope;
}
export function afterDiscovery(resolved, invalidate) {
  if (resolved.path !== db && !['control','no-reader'].includes(mode)) {
    throw Error('Fictional producer path assumption failed');
  }
  if (mode === 'revoked') invalidate(db);
  if (mode === 'alias' || mode === 'stable-handoff') {
    fs.symlinkSync(db,alias);
    // Paired correction: a producer that already possesses the admitted reader path
    // retains it instead of substituting another spelling across this handoff.
    return mode === 'alias' ? {...resolved,path:alias} : resolved;
  }
  if (mode === 'other-file' || mode === 'late-sibling') {
    const target = mode === 'late-sibling' ? sibling : '/home/replay/other.sqlite';
    const fixture = new DatabaseSync(target);
    try { fixture.exec('CREATE TABLE fictional(id INTEGER)'); } finally { fixture.close(); }
    return {...resolved,path:target};
  }
  return resolved;
}
