'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const target = path.join(root, '.env');
let text = fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : fs.readFileSync(path.join(root, '.env.example'), 'utf8');
for (const name of ['PET_MEMORY_ENCRYPTION_KEY', 'PET_API_TOKEN']) {
  if (new RegExp(`^${name}=\\s*$`, 'm').test(text)) text = text.replace(new RegExp(`^${name}=\\s*$`, 'm'), `${name}=${randomBytes(32).toString('hex')}`);
}
fs.writeFileSync(target, text, { mode: 0o600 });
fs.mkdirSync(path.join(root, '.runtime'), { recursive: true });
console.log('Private configuration ready: .env (secrets not printed)');
