'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const assert = require('node:assert/strict');
const { loadConfig } = require('../backend/config.cjs');
const { openDatabase } = require('../backend/upstream.cjs');
const { createMemoryStore } = require('../backend/memory-store.cjs');
const { createApp } = require('../backend/memory-server.cjs');

async function worker(phase) {
  const config = loadConfig();
  assert.ok(config.llm, 'LLM_NOT_CONFIGURED');
  const db = openDatabase(), store = createMemoryStore(db);
  const server = createApp({ store, llm: config.llm, token: config.token });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const steps = [];
  async function post(route, body) {
    const response = await fetch(base + route, { method: 'POST',
      headers: { authorization: `Bearer ${config.token}`, 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP_${response.status}`);
    return result;
  }
  async function remember(message, requestId) {
    const draft = await post('/api/remember', { message });
    assert.equal(draft.status, 'PENDING');
    const before = store.profile().revision;
    const result = await post('/api/confirm', { id: draft.id, requestId });
    assert.equal(result.revision, before + 1);
    steps.push({ action: 'remember_and_confirm', input: message, field: draft.field,
      confirmedValue: draft.value, revision: result.revision });
  }
  try {
    if (phase === 'write') {
      await remember('请记住，以后叫我小林。', 'live-name');
      await remember('请记住，我喜欢天文。', 'live-preference');
      assert.equal(store.profile().name, '小林');
      assert.ok(store.profile().preferences.some(item => item.value.includes('天文')));
      steps.push({ action: 'process_will_exit', profile: store.profile() });
    } else {
      assert.equal(store.profile().name, '小林');
      let response = await post('/api/chat', { message: '我叫什么，我喜欢什么？', sessionId: 'after-process-restart' });
      assert.ok(response.reply.includes('小林') && response.reply.includes('天文'), 'RECALL_NOT_GROUNDED');
      steps.push({ action: 'new_process_new_session_recall', ...response });
      await remember('更正一下，请记住以后叫我小禾，不要再叫我小林。', 'live-correction');
      assert.equal(store.profile().name, '小禾');
      response = await post('/api/chat', { message: '请只告诉我，现在应该怎么称呼我？', sessionId: 'after-process-restart' });
      assert.ok(response.reply.includes('小禾') && !response.reply.includes('小林'), 'CORRECTION_NOT_GROUNDED');
      steps.push({ action: 'corrected_name_recall', ...response });
      const draft = await post('/api/propose', { op: 'delete_all', expectedRevision: store.profile().revision });
      await post('/api/confirm', { id: draft.id, requestId: 'live-delete-all' });
      response = await post('/api/chat', { message: '你还记得我叫什么、喜欢什么吗？不知道就直说。', sessionId: 'after-process-restart' });
      assert.ok(!response.reply.includes('小林') && !response.reply.includes('小禾') && !response.reply.includes('天文'), 'DELETED_MEMORY_REAPPEARED');
      assert.equal(store.profile().name, null);
      steps.push({ action: 'deleted_profile_not_recalled', ...response });
    }
    return { phase, steps, usage: config.llm.usage };
  } finally {
    await new Promise(resolve => server.close(resolve));
    db.close();
  }
}

async function main() {
  if (process.argv[2] === '--worker') {
    console.log(JSON.stringify(await worker(process.argv[3])));
    return;
  }
  const root = path.resolve(__dirname, '..');
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'pet-live-'));
  const run = promisify(execFile);
  try {
    const phases = [];
    for (const phase of ['write', 'verify']) {
      const result = await run(process.execPath, [__filename, '--worker', phase], {
        cwd: root, env: { ...process.env, DB_PATH: path.join(folder, 'fictional.sqlite') }, timeout: 180_000, maxBuffer: 64 * 1024 });
      phases.push(JSON.parse(result.stdout.trim()));
    }
    const report = { checkedAt: new Date().toISOString(), ok: true, model: 'deepseek-flash',
      data: 'fictional', transport: 'real HTTP + official model API', processRestart: true,
      confirmation: 'test driver calls confirmation API; physical device not connected', phases };
    fs.mkdirSync(path.join(root, 'evaluation'), { recursive: true });
    fs.writeFileSync(path.join(root, 'evaluation', 'live-memory-result.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ ok: true, processRestart: true, report: 'evaluation/live-memory-result.json',
      requests: phases.reduce((total, phase) => total + phase.usage.requests, 0) }));
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
}

main().catch(error => {
  // Child stdout contains only fictional data; keep provider error bodies and credentials out of logs.
  console.error(error.stderr?.trim() || error.code || error.message);
  process.exitCode = 1;
});
