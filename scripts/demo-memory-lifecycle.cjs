'use strict';
// Fictional data and injected time only. Does not load .env or call a model.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { randomBytes } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const parent = path.join(root, '.runtime', 'checks');
fs.mkdirSync(parent, { recursive: true });
const folder = fs.mkdtempSync(path.join(parent, 'memory-lifecycle-'));
process.env.SANCTUARY_ENCRYPTION_KEY = randomBytes(32).toString('hex');
process.env.DB_PATH = path.join(folder, 'fictional.sqlite');
const { openDatabase } = require('../backend/upstream.cjs');
const { createMemoryStore } = require('../backend/memory-store.cjs');
let db;
try {
  db = openDatabase();
  const start = Date.UTC(2026, 0, 1);
  let now = start;
  const store = createMemoryStore(db, { now: () => now });
  function save(input) {
    const draft = store.propose({ ...input, expectedRevision: store.profile().revision });
    assert.equal(draft.status, 'PENDING');
    const result = store.confirm(draft.id, 'demo-' + draft.id);
    assert.equal(result.ok, true);
    return result;
  }
  save({ kind: 'profile', op: 'set', field: 'name', value: '小林', source: '请叫我小林', quote: '小林' });
  const event = save({ kind: 'experience', op: 'set', value: '今天一起看了猎户座',
    source: '请记住，今天一起看了猎户座', quote: '今天一起看了猎户座' });
  const samples = [];
  for (const day of [0, 7, 30]) {
    now = start + day * 86400000;
    const before = store.profile();
    const recall = store.recall('猎户座');
    assert.equal(recall.memories.length, 1);
    assert.equal(recall.profile.name, '小林');
    assert.deepEqual(store.profile(), before);
    assert.equal(store.recall('猎户座').memories[0].strength, recall.memories[0].strength);
    samples.push({ simulatedDay: day, strength: recall.memories[0].strength,
      ageDays: recall.memories[0].ageDays, name: recall.profile.name, text: recall.memories[0].text });
  }
  assert.equal(samples[0].strength, 1);
  assert.equal(samples[1].strength, 0.5);
  assert.ok(samples[2].strength > 0.05 && samples[2].strength < 0.052);
  store.reinforce(event.field, '又想起我们一起看了猎户座', '猎户座');
  const reinforced = store.recall('猎户座').memories[0];
  assert.equal(reinforced.strength, 1);
  assert.equal(reinforced.ageDays, 0);
  const draft = store.propose({ op: 'delete_all', expectedRevision: store.profile().revision });
  store.confirm(draft.id, 'demo-delete-' + draft.id);
  assert.equal(store.recall('猎户座').memories.length, 0);
  assert.equal(store.profile().name, null);
  const report = { ok: true, generatedAt: new Date().toISOString(), source: 'real_SQLite_and_pinned_memory_pipeline',
    fictionalData: true, simulatedTime: true, modelCalled: false, physicalDeviceConnected: false,
    humanForgettingValidated: false, halfLifeDays: 7, samples,
    reinforced: { simulatedDay: 30, strength: reinforced.strength, ageDays: reinforced.ageDays },
    readDoesNotReinforce: true, stableNamePreserved: true, deleteAllRemovesExperience: true,
    limits: 'Keyword retrieval still returns the matching older event. Weight decay is not deletion or a validated human forgetting curve.' };
  fs.writeFileSync(path.join(root, 'evaluation', 'memory-lifecycle-demo.json'), JSON.stringify(report, null, 2) + '\n');
  const rows = samples.map(x => `| 第${x.simulatedDay}天 | ${x.strength.toFixed(4)} | ${x.name} |`).join('\n');
  fs.mkdirSync(path.join(root, 'demo'), { recursive: true });
  fs.writeFileSync(path.join(root, 'demo', '记忆衰减回放.md'), `# 一段经历如何变淡\n\n这是独立SQLite测试库中注入时间的结果，使用虚构称呼“小林”和经历“今天一起看了猎户座”。不需要模型Key查看，也没有等待30天或修改电脑时间。\n\n| 模拟时间 | 经历权重 | 稳定称呼 |\n|---|---:|---|\n${rows}\n| 第30天主动重提后 | 1.0000 | 小林 |\n\n仅查看不会强化；明确重提并提供匹配证据后，权重恢复为1。删除全部后，经历和称呼都不能再被召回。\n\n这展示的是7天半衰期的工程规则：旧经历仍可被关键词命中，降权不等于删除，也不证明模型学会了人类遗忘。设备关系值单独计算，不受这张表驱动。\n\n复现：安装记忆依赖后运行\n\n\`\`\`powershell\n& ./.tools/node22/node-v22.23.4-win-x64/node.exe scripts/demo-memory-lifecycle.cjs\n\`\`\`\n\n[原始结果](../evaluation/memory-lifecycle-demo.json) · [实现](../backend/memory-store.cjs)\n`);
  console.log(JSON.stringify({ ok: true, samples: samples.length, simulatedTime: true, modelCalled: false,
    report: 'evaluation/memory-lifecycle-demo.json' }));
} finally {
  db?.close();
  // This fresh directory is generated inside the project's ignored check folder.
  assert.equal(path.dirname(folder), parent);
  fs.rmSync(folder, { recursive: true, force: true });
}
