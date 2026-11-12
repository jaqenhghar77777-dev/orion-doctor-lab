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
  const target=new Worker(new URL('./check-worker.mjs',import.meta.url),{workerData:{db,wait:true}});
  const bound=issue(db,scope,()=>{},new AbortController().signal,'safeguard',target.threadId);
  try {
    assert.ok(bound);
    await expect('different-worker-with-real-ticket',false,bound.ticket);
    const answer=new Promise((resolve,reject)=>{ target.once('message',resolve); target.once('error',reject); });
    target.postMessage(bound.ticket);
    assert.deepEqual(await answer,{allowed:true});
    console.log('SAFEGUARD assigned-worker-with-live-ticket allowed');
  } finally { bound?.close(); await target.terminate(); }
  await expect('same-pid-without-ticket',false);
  await expect('fabricated-ticket',false,randomUUID());
  assert.equal(issue(db,undefined,()=>{},new AbortController().signal),undefined);
  const unowned=createOpenClawDatabaseMaintenanceScope({schemaMaintenance:true});
  try { assert.equal(issue(db,unowned,()=>{},new AbortController().signal),undefined); }
  finally { await unowned.close(); }
  console.log('SAFEGUARD unowned-scope-cannot-mint refused');
  fs.mkdirSync(path.dirname(otherFile),{recursive:true});
  fs.writeFileSync(otherFile,raw,{flag:'wx'});
  await expect('other-database-copied-record',false,live.ticket,other);
  const cancel=new AbortController();
  const cancelled=mint(cancel.signal); cancel.abort();
  await expect('cancelled-task',false,cancelled.ticket);
  const settled=mint(); settled.close();
  await expect('settled-task',false,settled.ticket);
  await expect('still-held-before-release',true,live.ticket);
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

// A replacement can permanently revoke its original native owner. Keep this
// negative control independent from the release/replay and cancellation cases.
const swapped='/home/replay/replacement/state/openclaw.sqlite';
fs.mkdirSync(path.dirname(swapped),{recursive:true});
fs.copyFileSync('/fixture/state/openclaw.sqlite',swapped);
const swapOwner=acquireGatewayStateOwner({databasePath:swapped});
const swapScope=createOpenClawDatabaseMaintenanceScope({schemaMaintenance:true,
  assertDatabaseAccess:swapOwner.assertDatabaseAccess,assertOwnerCurrent:()=>swapOwner.assertCurrent()});
const swapFile=resolveGatewayStateOwnerPath(swapped);
const checked=issue(swapped,swapScope,()=>{},new AbortController().signal,'safeguard');
assert.ok(checked);
try {
  await expect('still-held-before-replacement',true,checked.ticket,swapped);
  const bytes=fs.readFileSync(swapFile);
  fs.renameSync(swapFile,swapFile+'.pinned');
  try {
    fs.writeFileSync(swapFile,bytes,{flag:'wx'});
    await expect('replaced-file-identical-bytes',false,checked.ticket,swapped);
  } finally { fs.renameSync(swapFile+'.pinned',swapFile); }
} finally {
  checked.close();
  try { await swapScope.close(); } finally { swapOwner.release(); }
}
