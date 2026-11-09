import { parentPort, workerData } from 'node:worker_threads';
import { assertStateDatabaseAccessAllowed } from './custody-api.mjs';
import worker from './custody-worker.cjs';
try {
  worker.run(workerData.ticket, () => assertStateDatabaseAccessAllowed(workerData.db));
  parentPort.postMessage({allowed:true});
} catch (e) {
  parentPort.postMessage({allowed:false, name:e.name, message:e.message});
}
