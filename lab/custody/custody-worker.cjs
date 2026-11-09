'use strict';
const { AsyncLocalStorage } = require('node:async_hooks');
const { createHash } = require('node:crypto');
const { isMainThread, postMessageToThread } = require('node:worker_threads');
const current = new AsyncLocalStorage();

exports.run = (ticket, operation) => {
  if (typeof ticket !== 'string') return operation();
  return current.run(ticket, operation);
};
exports.admit = (namespace, db, ownerPath, raw, owner) => {
  const ticket = current.getStore();
  if (isMainThread || process.platform !== 'linux' || !ticket || namespace !== 'unknown' ||
      owner.role !== 'sqlite-maintenance' || owner.processNamespace != null ||
      owner.pid !== process.pid || typeof owner.ownerId !== 'string') return false;
  const cell = new Int32Array(new SharedArrayBuffer(4));
  const message = {protocol:'orion-maintenance-owner-v1', db, ownerPath, ownerId:owner.ownerId,
    hash:createHash('sha256').update(raw).digest('hex'), ticket, decision:cell.buffer};
  try {
    // Destination zero is the actual main thread in this Node process. If it
    // cannot service this request, leave the normal maintenance refusal intact.
    void postMessageToThread(0, message, [], 3000).catch(() => {});
    Atomics.wait(cell, 0, 0, 3000);
    return Atomics.compareExchange(cell, 0, 0, 3) === 1;
  } catch { return false; }
};
