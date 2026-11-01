'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const folder = mkdtempSync(path.join(tmpdir(), 'pet-memory-'));
process.env.SANCTUARY_ENCRYPTION_KEY = randomBytes(32).toString('hex');
process.env.DB_PATH = path.join(folder, 'test.sqlite');
let now = 1_800_000_000_000;
const { openDatabase } = require('../backend/upstream.cjs');
const { createMemoryStore } = require('../backend/memory-store.cjs');
const db = openDatabase();
const store = createMemoryStore(db, { now: () => now });
after(() => { db.close(); rmSync(folder, { recursive: true, force: true }); });

function proposal(field, value, extra = {}) {
  return store.propose({ field, value, source: `请记住：${value}`, quote: value,
    expectedRevision: store.profile().revision, ...extra });
}
function confirm(draft, requestId = draft.id) { return store.confirm(draft.id, requestId); }

test('草稿不改变资料；确认后经上游证据协议可召回，并支持重复确认幂等', () => {
  const draft = proposal('name', '小林');
  assert.equal(store.profile().name, null);
  const result = confirm(draft, 'confirm-name-1');
  assert.equal(store.profile().name, '小林');
  assert.deepEqual(store.confirm(draft.id, 'confirm-name-1'), result);
  assert.equal(store.profile().revision, 1);
  const claims = db.prepare('SELECT * FROM memory_claims').all();
  assert.equal(claims.length, 1);
  assert.equal(claims[0].support_state, 'supported');
  assert.equal(db.prepare('SELECT COUNT(*) n FROM memory_search_projection').get().n, 1);
  assert.ok(store.recall('我叫什么').context.includes('小林'));
});

test('重建适配器后资料仍在，不依赖旧会话；更正不再召回旧称呼', () => {
  const restarted = createMemoryStore(db, { now: () => now });
  assert.equal(restarted.profile().name, '小林');
  confirm(proposal('name', '小禾'));
  assert.equal(store.profile().name, '小禾');
  assert.ok(!store.recall('小林').context.includes('小林'));
});

test('未确认删除、超时和取消不能误删；真正删除后新会话不能复活', () => {
  let draft = proposal('name', '', { op: 'delete', source: '', quote: '' });
  assert.equal(store.profile().name, '小禾');
  store.cancel(draft.id);
  assert.throws(() => confirm(draft), /NOT_FOUND/);
  draft = proposal('name', '', { op: 'delete', source: '', quote: '' });
  now += 30_001;
  assert.throws(() => confirm(draft), /EXPIRED/);
  assert.equal(store.profile().name, '小禾');
  confirm(proposal('name', '', { op: 'delete', source: '', quote: '' }));
  assert.equal(createMemoryStore(db).profile().name, null);
  assert.ok(!store.recall('小禾').context.includes('小禾'));
});

test('拒绝超长UTF8、非原文证据、任意字段和并行草稿', () => {
  assert.throws(() => proposal('name', '啊'.repeat(9)), /TOO_LONG/);
  assert.throws(() => proposal('preference0', '喜欢天文', { quote: '不存在的原文' }), /EVIDENCE/);
  assert.throws(() => proposal('__proto__', 'bad'), /FIELD/);
  const draft = proposal('preference0', '喜欢天文');
  assert.throws(() => proposal('preference1', '喜欢音乐'), /BUSY/);
  store.cancel(draft.id);
});

test('revision冲突、确认ID重用不能覆盖新资料', () => {
  const revision = store.profile().revision;
  assert.throws(() => proposal('name', '旧资料', { expectedRevision: revision - 1 }), /CONFLICT/);
  const draft = proposal('name', '小林');
  assert.throws(() => confirm(draft, 'confirm-name-1'), /CONFLICT/);
  store.cancel(draft.id);
});

test('经历随虚拟时间降权、重提强化；稳定资料不遗忘；仅检索不自我强化', () => {
  confirm(proposal('name', '小林'));
  const draft = proposal(null, '今天一起看了猎户座', { kind: 'experience' });
  const saved = confirm(draft);
  const before = store.recall('猎户座');
  now += 7 * 86_400_000;
  const later = store.recall('猎户座');
  assert.ok(later.memories[0].strength < before.memories[0].strength);
  assert.equal(store.recall('猎户座').memories[0].strength, later.memories[0].strength);
  store.reinforce(saved.field, '用户再次提到猎户座', '猎户座');
  assert.ok(store.recall('猎户座').memories[0].strength > later.memories[0].strength);
  assert.equal(store.profile().name, '小林');
});

test('全部删除移除资料、经历与召回投影，磁盘不能残留明文资料', () => {
  confirm(proposal(null, '', { op: 'delete_all', source: '', quote: '' }));
  assert.equal(store.profile().name, null);
  assert.equal(store.recall('猎户座').memories.length, 0);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM memory_search_projection').get().n, 0);
  db.pragma('wal_checkpoint(TRUNCATE)');
  const disk = readFileSync(process.env.DB_PATH);
  for (const secret of ['小林', '小禾', '猎户座']) assert.ok(!disk.includes(Buffer.from(secret)));
});
