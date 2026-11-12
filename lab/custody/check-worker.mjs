import { parentPort, workerData } from 'node:worker_threads';
import { assertStateDatabaseAccessAllowed } from './custody-api.mjs';
import worker from './custody-worker.cjs';
function check(ticket) {
  try {
    worker.run(ticket, () => assertStateDatabaseAccessAllowed(workerData.db));
    parentPort.postMessage({allowed:true});
  } catch (e) {
    parentPort.postMessage({allowed:false, name:e.name, message:e.message});
  }
}
if (workerData.wait) parentPort.once('message', check);
else check(workerData.ticket);
