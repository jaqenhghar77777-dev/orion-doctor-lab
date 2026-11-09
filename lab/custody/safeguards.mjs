import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { Worker } from 'node:worker_threads';
import { acquireGatewayStateOwner, resolveGatewayStateOwnerPath, createOpenClawDatabaseMaintenanceScope } from './custody-api.mjs';
import { issue } from './custody-host.mjs';

fs.writeFileSync('/home/replay/.simulate-missing-pid-link','');
const db = path.join(process.env.OPENCLAW_STATE_DIR, 'state/openclaw.sqlite');
const other = '/home/replay/second/state/openclaw.sqlite';
for (const file of [db,other]) {
  fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.copyFileSync('/fixture/state/openclaw.sqlite',file);
}
async function expect(label, expected, ticket, dbPath = db) {
  const thread = new Worker(new URL('./check-worker.mjs', import.meta.url), {workerData:{ticket,db:dbPath}});
  try {
    const result = await new Promise((resolve,reject) => {
      thread.once('error', reject);
      thread.once('message', resolve);
      thread.once('exit', code => reject(Error('Worker exited without a result: '+code)));
    });
    assert.equal(result.allowed,expected,label+' '+JSON.stringify(result));
    if (!expected) {
      assert.equal(result.name,'StateDatabaseAccessError',label);
      assert.match(result.message,/undergoing offline maintenance by sqlite-maintenance/);
    }
    console.log('SAFEGUARD',label,expected?'allowed':'refused');
  } finally { await thread.terminate(); }
}
const lease=acquireGatewayStateOwner({databasePath:db});
const scope=createOpenClawDatabaseMaintenanceScope({schemaMaintenance:true,
  assertDatabaseAccess:lease.assertDatabaseAccess, assertOwnerCurrent:() => lease.assertCurrent()});
const file=resolveGatewayStateOwnerPath(db), otherFile=resolveGatewayStateOwnerPath(other);
assert.notEqual(file,otherFile);
const raw=fs.readFileSync(file);
assert.equal(JSON.parse(raw).processNamespace,null);
let released=false;
const grants=[];
function mint(signal=new AbortController().signal) {
  const grant=scope.run(()=>issue(db,scope,()=>signal.throwIfAborted(),signal,'safeguard'));
  assert.ok(grant,'host failed to mint under its own active scope');
  grants.push(grant); return grant;
}
try {
  const live=mint();
  await expect('live-host-and-task',true,live.ticket);
  await expect('same-pid-without-ticket',false);
  await expect('fabricated-ticket',false,randomUUID());
  assert.equal(issue(db,undefined,()=>{},new AbortController().signal),undefined);
  fs.mkdirSync(path.dirname(otherFile),{recursive:true});
  fs.writeFileSync(otherFile,raw,{flag:'wx'});
  await expect('other-database-copied-record',false,live.ticket,other);
  fs.renameSync(file,file+'.pinned');
  try {
    fs.writeFileSync(file,raw,{flag:'wx'});
    await expect('replaced-file-identical-bytes',false,live.ticket);
  } finally { fs.renameSync(file+'.pinned',file); }
  const cancel=new AbortController();
  const cancelled=mint(cancel.signal); cancel.abort();
  await expect('cancelled-task',false,cancelled.ticket);
  const settled=mint(); settled.close();
  await expect('settled-task',false,settled.ticket);
  lease.release(); released=true;
  fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.writeFileSync(file,raw,{flag:'wx'});
  await expect('released-owner-replayed-record',false,live.ticket);
  assert.equal(issue(db,scope,()=>{},new AbortController().signal),undefined);
  const unrelated=createOpenClawDatabaseMaintenanceScope({schemaMaintenance:true});
  try {
    assert.equal(issue(db,unrelated,()=>{},new AbortController().signal),undefined);
  } finally { await unrelated.close(); }
  console.log('SAFEGUARD foreign-record-cannot-mint refused');
} finally {
  for(const grant of grants) grant.close();
  if(!released) lease.release();
  await scope.close();
}
