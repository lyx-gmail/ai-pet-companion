'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { randomBytes } = require('node:crypto');
const folder = mkdtempSync(path.join(tmpdir(), 'pet-http-'));
process.env.SANCTUARY_ENCRYPTION_KEY = randomBytes(32).toString('hex');
process.env.DB_PATH = path.join(folder, 'test.sqlite');
const { openDatabase } = require('../backend/upstream.cjs');
const { createMemoryStore } = require('../backend/memory-store.cjs');
const { createApp } = require('../backend/memory-server.cjs');
const db = openDatabase();
const store = createMemoryStore(db);
const calls = [];
// Protocol double: assertions below prove HTTP/data wiring, not a real model's intelligence.
const llm = { complete: async (messages, { json = false } = {}) => {
  calls.push(messages);
  return json ? JSON.stringify({ remember: true, kind: 'profile', field: 'name', value: '小林', quote: '叫我小林' }) : '已收到当前会话的记忆上下文';
} };
const token = randomBytes(32).toString('hex');
const server = createApp({ store, llm, token });
let base;
const ready = new Promise(resolve => server.listen(0, '127.0.0.1', () => { base = `http://127.0.0.1:${server.address().port}`; resolve(); }));
after(async () => { await new Promise(resolve => server.close(resolve)); db.close(); rmSync(folder, { recursive: true, force: true }); });
async function request(route, data, auth = true, extra = {}) {
  await ready;
  return fetch(base + route, { method: data ? 'POST' : 'GET', headers: { 'content-type': 'application/json',
    ...(auth ? { authorization: `Bearer ${token}` } : {}), ...extra }, ...(data ? { body: JSON.stringify(data) } : {}) });
}

test('健康检查无资料；私有接口必须鉴权且拒绝跨站Origin', async () => {
  const health = await (await request('/health', null, false)).json();
  assert.deepEqual(Object.keys(health).sort(), ['llmConfigured', 'ok']);
  assert.equal((await request('/api/profile', null, false)).status, 401);
  assert.equal((await request('/api/profile', null, true, { origin: 'https://example.com' })).status, 403);
});

test('模型提取只生成草稿；实体确认契约完成后，新会话确定性注入资料', async () => {
  const draft = await (await request('/api/remember', { message: '请记住，以后叫我小林' })).json();
  assert.equal(draft.status, 'PENDING');
  assert.equal((await (await request('/api/profile')).json()).name, null);
  assert.equal((await request('/api/confirm', { id: draft.id, requestId: 'http-confirm-1' })).status, 200);
  for (const sessionId of ['first-session', 'brand-new-session']) {
    const response = await request('/api/chat', { message: '我叫什么？', sessionId });
    assert.equal(response.status, 200);
    assert.ok(calls.at(-1).some(message => message.content.includes('小林')));
  }
});

test('模型未配置时不伪造回答，受控资料仍可读取', async () => {
  const offline = createApp({ store, llm: null, token });
  await new Promise(resolve => offline.listen(0, '127.0.0.1', resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${offline.address().port}/api/chat`, { method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' }, body: JSON.stringify({ message: '你好' }) });
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, 'LLM_NOT_CONFIGURED');
  } finally { await new Promise(resolve => offline.close(resolve)); }
});

test('删除后清除历史会话，后续问题不再注入旧称呼', async () => {
  const draft = await (await request('/api/propose', { op: 'delete_all', expectedRevision: store.profile().revision })).json();
  await request('/api/confirm', { id: draft.id, requestId: 'http-delete-all' });
  await request('/api/chat', { message: '我叫什么？', sessionId: 'first-session' });
  assert.ok(calls.at(-1).every(message => !message.content.includes('小林')));
});

test('中文字符跨请求数据块时仍保留完整内容', async () => {
  await ready;
  const payload = Buffer.from(JSON.stringify({ message: '你好', sessionId: 'split-utf8' }));
  const cut = payload.indexOf(Buffer.from('你')) + 1;
  const result = await new Promise((resolve, reject) => {
    const req = http.request(base + '/api/chat', { method: 'POST', headers: {
      authorization: `Bearer ${token}`, 'content-type': 'application/json'
    } }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); });
    req.on('error', reject);
    req.write(payload.subarray(0, cut));
    setTimeout(() => req.end(payload.subarray(cut)), 30);
  });
  assert.equal(result, 200);
  assert.equal(calls.at(-1).at(-1).content, '你好');
});
