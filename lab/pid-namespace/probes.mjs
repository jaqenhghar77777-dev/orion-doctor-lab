import fs from 'node:fs';
import assert from 'node:assert/strict';
import { syncBuiltinESMExports } from 'node:module';

const [mode, peerJson] = process.argv.slice(2);
const link = '/proc/self/ns/pid';
const directory = '/proc/self/ns';
const boot = '/proc/sys/kernel/random/boot_id';
const absent = '/proc/self/ns/orion_replay_missing_pid';
const nativeReadlink = fs.readlinkSync.bind(fs);
const nativeStat = fs.statSync.bind(fs);
const nativeRead = fs.readFileSync.bind(fs);
const actual = nativeReadlink(link);
assert.match(actual, /^pid:\[\d+\]$/);
const err = code => Object.assign(new Error(code), {code});
// Exercise the same published beta API in a fresh process per condition.
if (mode !== 'visible') fs.writeFileSync('/home/replay/.simulate-missing-pid-link','');
if (mode === 'link-denied') {
  fs.readlinkSync = (file,...args) => {
    if (file === absent) throw err('EACCES');
    return nativeReadlink(file,...args);
  };
}
if (mode === 'directory-missing') {
  fs.statSync = (file,...args) => {
    if (file === directory) throw err('ENOENT');
    return nativeStat(file,...args);
  };
}
if (mode === 'boot-denied') {
  fs.readFileSync = (file,...args) => {
    if (file === boot) throw err('EACCES');
    return nativeRead(file,...args);
  };
}
syncBuiltinESMExports();
const {read, classify} = await import('./api.mjs');
const own = read();
if (['link-denied','directory-missing','boot-denied'].includes(mode)) {
  assert.equal(own, null);
  assert.equal(classify({platform:'linux',host:'orion-replay',identity:'00000000-0000-4000-8000-000000000001',pidNsInode:'unsupported'}), 'unknown');
  console.log('PROBE',mode,'unknown');
} else if (mode === 'visible') {
  assert.equal(own.pidNsInode, actual.match(/\d+/)[0]);
  assert.equal(classify(own), 'same');
  console.log('PROBE visible matched-native-inode');
} else if (mode === 'missing') {
  assert.equal(own.pidNsInode, 'unsupported');
  assert.equal(classify(own), 'same');
  assert.equal(classify(null), 'unknown');
  assert.equal(classify({...own,host:own.host + '-other'}), 'unknown');
  assert.equal(classify({...own,identity:'00000000-0000-4000-8000-000000000001'}), 'dead');
  console.log('PROBE missing same-host-and-boot=same legacy-null=unknown foreign-host=unknown different-boot=dead');
} else if (mode === 'peer') {
  assert.equal(own.pidNsInode,'unsupported');
  console.log('PEER '+JSON.stringify({actual,own}));
  setInterval(()=>{},30000);
} else if (mode === 'compare') {
  const peer = JSON.parse(peerJson);
  assert.notEqual(peer.actual,actual,'must be two distinct real Linux PID namespaces');
  assert.equal(peer.own.host,own.host);
  assert.equal(peer.own.identity,own.identity);
  assert.equal(peer.own.pidNsInode,'unsupported');
  assert.equal(own.pidNsInode,'unsupported');
  const decision = classify(peer.own);
  console.log('ISOLATION '+JSON.stringify({sameHost:true,sameBoot:true,distinctActualPidNamespaces:true,peerClassified:decision}));
  if (decision !== 'unknown') process.exitCode=3;
} else {
  throw Error('unrecognized test mode '+mode);
}
