// Laboratory candidate. The adapter imports the pinned beta's actual owner registry.
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { isMainThread } from 'node:worker_threads';
import { captureGatewayStateOwner, resolveGatewayStateOwnerPath, getOpenClawDatabaseMaintenanceScope } from './custody-api.mjs';

const grants = new Map();
const protocol = 'orion-maintenance-owner-v1';
const digest = value => createHash('sha256').update(value).digest('hex');
let listening = false;

function record(event, kind, detail) {
  try { fs.appendFileSync('/tmp/orion-custody.jsonl', JSON.stringify({event, kind, detail}) + '\n'); } catch {}
}
function serve(message, sender) {
  if (sender <= 0 || message?.protocol !== protocol ||
      !(message.decision instanceof SharedArrayBuffer) || message.decision.byteLength !== 4) return;
  const cell = new Int32Array(message.decision);
  if (Atomics.load(cell, 0) !== 0) return;
  const grant = grants.get(message.ticket);
  let allowed = false;
  try { allowed = grant?.verify(message) === true; }
  catch { allowed = false; }
  if (Atomics.compareExchange(cell, 0, 0, allowed ? 1 : 2) === 0) {
    record(allowed ? 'granted' : 'denied', grant?.kind || 'unregistered', sender);
    Atomics.notify(cell, 0);
  }
}

// The ticket exists only while this admitted task is outstanding. Each worker
// check goes back to the live host. A UUID present in a lock file is never a ticket.
export function issue(databasePath, scope, assertTask, signal, kind = 'read') {
  if (!isMainThread || process.platform !== 'linux' || !scope?.ownsSchemaMaintenance) return;
  const db = path.resolve(databasePath);
  let fd;
  let grant;
  try {
    scope.run(() => {
      if (getOpenClawDatabaseMaintenanceScope() !== scope) throw Error('scope is not current');
      const file = resolveGatewayStateOwnerPath(db);
      const initial = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (initial.processNamespace != null || initial.role !== 'sqlite-maintenance') return;
      const owner = captureGatewayStateOwner(db);
      if (!owner || owner.role !== 'sqlite-maintenance' || !owner.ownerId ||
          owner.ownerId !== initial.ownerId || initial.pid !== process.pid) return;
      const assertLive = () => {
        signal?.throwIfAborted();
        owner.signal.throwIfAborted();
        assertTask();
        scope.assertDatabaseAccess(db);
        owner.assertCurrent();
      };
      assertLive();
      fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      const pinned = fs.fstatSync(fd, {bigint:true});
      if (!pinned.isFile() || pinned.size <= 0n || pinned.size > 65536n) throw Error('invalid sidecar');
      const bytes = Buffer.alloc(Number(pinned.size));
      if (fs.readSync(fd, bytes, 0, bytes.length, 0) !== bytes.length) throw Error('short owner record');
      const payload = JSON.parse(bytes);
      if (payload.ownerId !== owner.ownerId || payload.role !== 'sqlite-maintenance' ||
          payload.pid !== process.pid || payload.processNamespace != null) throw Error('owner changed');
      const signature = digest(bytes);
      const sameFile = () => {
        const current = fs.lstatSync(file, {bigint:true});
        return current.isFile() && current.dev === pinned.dev && current.ino === pinned.ino;
      };
      if (!sameFile()) throw Error('owner file changed');
      assertLive();
      const ticket = randomUUID();
      const close = () => {
        if (!grants.delete(ticket)) return;
        signal?.removeEventListener('abort', close);
        owner.signal.removeEventListener('abort', close);
        fs.closeSync(fd);
        fd = undefined;
      };
      const recheck = () => scope.run(() => {
          if (!grants.has(ticket) || getOpenClawDatabaseMaintenanceScope() !== scope) throw Error('task retired');
          assertLive();
          if (!sameFile() || digest(fs.readFileSync(file)) !== signature || !sameFile()) throw Error('owner file changed');
          assertLive();
          if (!grants.has(ticket)) throw Error('task retired');
        });
      const verify = message => {
        if (message.db !== db || message.ownerPath !== file || message.ownerId !== owner.ownerId ||
            message.hash !== signature) return false;
        recheck();
        return true;
      };
      if (!listening) {
        process.on('workerMessage', serve);
        listening = true;
      }
      grants.set(ticket, {verify, kind});
      signal?.addEventListener('abort', close, {once:true});
      owner.signal.addEventListener('abort', close, {once:true});
      grant = {ticket, close, assertCurrent:recheck};
      record('issued', kind);
    });
  } catch (error) {
    record('issue-refused', kind, error.message);
    grant?.close();
    grant = undefined;
  } finally {
    if (!grant && fd !== undefined) fs.closeSync(fd);
  }
  return grant;
}
