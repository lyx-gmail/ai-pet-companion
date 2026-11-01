'use strict';
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const upstreamDir = path.join(root, '.tools', 'upstream', 'MemoryConstellations');
const upstream = file => require(path.join(upstreamDir, file));

function quiet(fn) {
  const log = console.log;
  try { console.log = () => {}; return fn(); } finally { console.log = log; }
}

function openDatabase() {
  const key = process.env.SANCTUARY_ENCRYPTION_KEY;
  if (!/^[a-f\d]{64}$/i.test(key || '')) throw new Error('MEMORY_ENCRYPTION_KEY_REQUIRED');
  const encryption = quiet(() => upstream('encryption.js').encryption);
  // Upstream encryption returns plaintext on failure. Fail closed while preserving its ciphertext format.
  encryption.encrypt = text => {
    if (text === '') return '';
    if (typeof text !== 'string') throw new Error('ENCRYPTION_INPUT_INVALID');
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv('aes-256-gcm', Buffer.from(key, 'hex'), iv);
    const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
    return `enc:${iv.toString('hex')}:${cipher.getAuthTag().toString('hex')}:${encrypted.toString('hex')}`;
  };
  encryption.decrypt = text => {
    if (typeof text !== 'string' || !text.startsWith('enc:')) throw new Error('CIPHERTEXT_REQUIRED');
    const parts = text.split(':');
    if (parts.length !== 4) throw new Error('CIPHERTEXT_INVALID');
    const decipher = crypto.createDecipheriv('aes-256-gcm', Buffer.from(key, 'hex'), Buffer.from(parts[1], 'hex'));
    decipher.setAuthTag(Buffer.from(parts[2], 'hex'));
    return Buffer.concat([decipher.update(Buffer.from(parts[3], 'hex')), decipher.final()]).toString('utf8');
  };
  return quiet(() => upstream('database.js').initDatabase());
}

module.exports = { upstream, upstreamDir, openDatabase, quiet };
