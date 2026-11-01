'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createLlm } = require('../backend/llm.cjs');

test('OpenAI兼容HTTP契约：携带模型／鉴权／JSON模式，错误不回显服务端正文或密钥', async () => {
  let received;
  const server = http.createServer(async (req, res) => {
    let text = ''; for await (const chunk of req) text += chunk;
    received = { path: req.url, auth: req.headers.authorization, body: JSON.parse(text) };
    res.setHeader('content-type', 'application/json');
    if (received.body.model === 'bad') { res.statusCode = 401; res.end('{"error":"PRIVATE_KEY_MUST_NOT_LEAK"}'); }
    else res.end(JSON.stringify({ choices: [{ message: { content: '{"ok":true}' } }] }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const baseUrl = `http://127.0.0.1:${server.address().port}/v1`;
    const llm = createLlm({ baseUrl, apiKey: 'fictional-key', model: 'test-model' });
    assert.equal(await llm.complete([{ role: 'user', content: '协议测试' }], { json: true }), '{"ok":true}');
    assert.equal(received.path, '/v1/chat/completions');
    assert.equal(received.auth, 'Bearer fictional-key');
    assert.equal(received.body.response_format.type, 'json_object');
    await assert.rejects(createLlm({ baseUrl, apiKey: 'fictional-key', model: 'bad' }).complete([]), /^Error: LLM_HTTP_401$/);
    assert.throws(() => createLlm({ baseUrl: 'http://untrusted.example/v1', apiKey: 'x', model: 'm' }), /HTTPS/);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
