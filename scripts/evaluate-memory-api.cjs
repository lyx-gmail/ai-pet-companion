'use strict';
// Real configured model, isolated RAM database. Never connected to the pet.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
process.env.DB_PATH = ':memory:';
const { loadConfig } = require('../backend/config.cjs');
const { openDatabase } = require('../backend/upstream.cjs');
const { createMemoryStore } = require('../backend/memory-store.cjs');
const { createApp } = require('../backend/memory-server.cjs');
const root = path.resolve(__dirname, '..');

async function main() {
  const config = loadConfig();
  assert.ok(config.llm, 'LLM_NOT_CONFIGURED');
  const cases = JSON.parse(fs.readFileSync(path.join(root, 'evaluation/ai-cases.json'), 'utf8')).cases;
  const db = openDatabase(), store = createMemoryStore(db);
  const server = createApp({ store, llm: config.llm, token: config.token });
  const report = { source: 'configured_real_model_isolated_RAM_HTTP_memory_API',
    fictionalData: true, physicalDeviceConnected: false, confirmation: 'programmatic_test_driver',
    model: process.env.PET_LLM_MODEL, full30CasesVerified: false, manualScoresAssigned: false,
    cases: [], completed: false, usage: null };
  let sequence = 0;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    async function post(route, value) {
      const response = await fetch(base + '/api/' + route, { method: 'POST',
        headers: { authorization: `Bearer ${config.token}`, 'content-type': 'application/json' },
        body: JSON.stringify(value), signal: AbortSignal.timeout(40_000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'HTTP_FAILED');
      return data;
    }
    async function confirm(draft) {
      return post('confirm', { id: draft.id, requestId: 'eval-' + draft.id });
    }
    async function seed(field, value) {
      const draft = await post('propose', { kind: 'profile', op: 'set', field, value,
        source: `测试前置资料：${value}`, quote: value, expectedRevision: store.profile().revision });
      return confirm(draft);
    }
    async function draftCase(id, field, value) {
      const definition = cases.find(item => item.id === id), before = store.profile();
      const observation = { id, input: definition.input, before, executionScope: 'memory_HTTP_text_fixture',
        productAcceptance: 'not_verified', naturalness_1_to_5: null, personality_1_to_5: null };
      report.cases.push(observation);
      const draft = await post('remember', { message: definition.input });
      observation.proposal = draft;
      assert.equal(draft.status, 'PENDING');
      assert.equal(draft.field, field);
      assert.ok((Array.isArray(value) ? value : [value]).includes(draft.value), 'PROPOSAL_VALUE_MISMATCH');
      assert.deepEqual(store.profile(), before, 'DRAFT_CHANGED_PROFILE');
      observation.checks = { proposalMatches: true, noWriteBeforeConfirmation: true };
      observation.programmaticConfirmation = await confirm(draft);
      observation.after = store.profile();
      assert.equal(observation.after.revision, before.revision + 1);
      observation.checks.confirmedRevisionAdvancedOnce = true;
      console.log(JSON.stringify({ observed: id, scope: observation.executionScope }));
    }
    async function chatCase(id, check) {
      const definition = cases.find(item => item.id === id), before = store.profile();
      const observation = { id, input: definition.input, before, executionScope: 'memory_HTTP_text_fixture',
        productAcceptance: 'needs_manual_review', naturalness_1_to_5: null, personality_1_to_5: null };
      report.cases.push(observation);
      observation.response = await post('chat', { message: definition.input, sessionId: 'eval-' + (++sequence) });
      observation.after = store.profile();
      assert.deepEqual(observation.after, before, 'READ_CHANGED_PROFILE');
      observation.checks = { profileUnchanged: true, memoryRevisionMatches: observation.response.memoryRevision === before.revision,
        ...check(observation.response.reply) };
      console.log(JSON.stringify({ observed: id, scope: observation.executionScope }));
    }
    await draftCase('MEM01', 'name', '小林');
    await chatCase('MEM02', reply => ({ containsConfirmedName: reply.includes('小林') }));
    await draftCase('MEM03', 'preference0', ['天文', '喜欢天文']);
    // MEM04 requires a separate process restart; this RAM fixture cannot prove it.
    await draftCase('MEM05', 'name', '小禾');
    await chatCase('MEM06', reply => ({ containsCurrentName: reply.includes('小禾'), doesNotUseOldName: !reply.includes('小林') }));
    await seed('preference1', '爵士');
    const deletion = await post('propose', { op: 'delete', field: 'preference0', expectedRevision: store.profile().revision });
    await confirm(deletion);
    await chatCase('MEM07', reply => ({ containsRemainingPreference: reply.includes('爵士'), doesNotUseDeletedPreference: !reply.includes('天文') }));
    await confirm(await post('propose', { op: 'delete_all', expectedRevision: store.profile().revision }));
    await chatCase('MEM08', reply => ({ noDeletedNamesOrPreferences: !['小林', '小禾', '天文', '爵士'].some(value => reply.includes(value)) }));
    report.completed = true;
  } catch (error) {
    report.error = /^[A-Z][A-Z_0-9]*$/.test(error.message || '') ? error.message : 'EVALUATION_FAILED';
    process.exitCode = 1;
  } finally {
    report.usage = config.llm.usage;
    report.generatedAt = new Date().toISOString();
    await new Promise(resolve => server.close(resolve));
    db.close();
    fs.writeFileSync(path.join(root, 'evaluation/memory-api-evaluation.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ completed: report.completed, cases: report.cases.length,
      requests: report.usage.requests, fullProductAcceptance: false }));
  }
}
main().catch(() => { console.error('EVALUATION_START_FAILED'); process.exitCode = 1; });
