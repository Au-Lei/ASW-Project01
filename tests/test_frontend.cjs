// Offline checks for network retry policy; no browser or AI service required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({ setTimeout: callback => callback() });
vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/api.js'), 'utf8'), context);

(async () => {
  let calls = 0;
  context.fetch = async () => {
    calls++;
    if (calls < 3) throw new Error('network failed');
    return { ok: true };
  };
  assert.equal((await vm.runInContext("networkFetch('/api/stats')", context)).ok, true);
  assert.equal(calls, 3);

  calls = 0;
  context.fetch = async () => { calls++; throw new Error('network failed'); };
  await assert.rejects(vm.runInContext("api('/api/extract/start', {})", context), /无法连接本机服务/);
  assert.equal(calls, 1, 'POST must not duplicate an extraction request');

  calls = 0;
  context.fetch = async () => {
    calls++;
    return { ok: false, json: async () => ({ error: '文件类型无效' }) };
  };
  await assert.rejects(vm.runInContext("api('/api/extract/start', {})", context), /文件类型无效/);
  assert.equal(calls, 1);
  console.log('Frontend API: 3 checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
