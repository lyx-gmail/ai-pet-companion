'use strict';

function createLlm({ baseUrl, apiKey, model, timeoutMs = 30_000 }) {
  const endpoint = new URL(baseUrl);
  if (endpoint.protocol !== 'https:' && !(endpoint.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname))) {
    throw new Error('LLM_HTTPS_REQUIRED');
  }
  if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw new Error('LLM_ENDPOINT_INVALID');
  if (typeof apiKey !== 'string' || !apiKey.trim() || typeof model !== 'string' || !model.trim()) throw new Error('LLM_CONFIG_REQUIRED');
  endpoint.pathname = endpoint.pathname.replace(/\/$/, '') + '/chat/completions';
  const client = { usage: { requests: 0, promptTokens: 0, completionTokens: 0 }, lastUsage: null };
  client.complete = async (messages, { json = false } = {}) => {
    const started = Date.now();
    let response;
    try {
      response = await fetch(endpoint, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(timeoutMs),
        headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
        body: JSON.stringify({ model, messages, max_tokens: json ? 1024 : 512,
          ...(json ? { response_format: { type: 'json_object' } } : {}),
          ...(endpoint.hostname === 'api.deepseek.com' ? { thinking: { type: 'disabled' } } : {}) }) });
    } catch (error) { throw new Error(error.name === 'TimeoutError' ? 'LLM_TIMEOUT' : 'LLM_NETWORK_ERROR'); }
    if (!response.ok) { await response.body?.cancel(); throw new Error(`LLM_HTTP_${response.status}`); }
    const chunks = []; let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > 131_072) throw new Error('LLM_RESPONSE_TOO_LARGE');
      chunks.push(chunk);
    }
    let data;
    try { data = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new Error('LLM_RESPONSE_INVALID'); }
    const content = data.choices?.[0]?.message?.content;
    if (typeof content !== 'string' || !content.trim() || data.choices[0].finish_reason === 'length') throw new Error('LLM_RESPONSE_INVALID');
    client.lastUsage = { promptTokens: Number(data.usage?.prompt_tokens || 0),
      completionTokens: Number(data.usage?.completion_tokens || 0), durationMs: Date.now() - started };
    client.usage.requests++;
    client.usage.promptTokens += client.lastUsage.promptTokens;
    client.usage.completionTokens += client.lastUsage.completionTokens;
    return content;
  };
  return client;
}
module.exports = { createLlm };
