'use strict';
const path = require('node:path');
const fs = require('node:fs');
const { upstream } = require('./upstream.cjs');
const { createLlm } = require('./llm.cjs');

function loadConfig() {
  const root = path.resolve(__dirname, '..');
  upstream('node_modules/dotenv/lib/main.js').config({ path: path.join(root, '.env') });
  const key = process.env.PET_MEMORY_ENCRYPTION_KEY;
  const token = process.env.PET_API_TOKEN;
  if (!/^[a-f\d]{64}$/i.test(key || '') || !/^[a-f\d]{64}$/i.test(token || '')) throw new Error('RUN_PRIVATE_SETUP_FIRST');
  process.env.SANCTUARY_ENCRYPTION_KEY = key;
  fs.mkdirSync(path.join(root, '.runtime'), { recursive: true });
  process.env.DB_PATH ||= path.join(root, '.runtime', 'pet.sqlite');
  const llm = process.env.PET_LLM_API_KEY ? createLlm({ baseUrl: process.env.PET_LLM_BASE_URL,
    apiKey: process.env.PET_LLM_API_KEY, model: process.env.PET_LLM_MODEL }) : null;
  const port = Number(process.env.PET_PORT || 8766);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('PORT_INVALID');
  return { root, token, port, llm };
}
module.exports = { loadConfig };
