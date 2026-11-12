// Test fixture only. Mounted by CI so even the launcher's direct Node probe
// observes ENOENT; normal post-migration session reads may never ask for it.
const fs = require('node:fs');
for (const name of ['readlinkSync','statSync']) {
  const original = fs[name];
  fs[name] = function(file,...args) {
    if (file === '/proc/self/ns/pid')
      throw Object.assign(new Error('ENOENT: simulated absent PID namespace link'),{code:'ENOENT'});
    return original.call(this,file,...args);
  };
}
require('node:module').syncBuiltinESMExports();
