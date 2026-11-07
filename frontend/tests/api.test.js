import test from 'node:test';
import assert from 'node:assert/strict';
import { api, readEventStream } from '../src/api.js';
import { FALLBACK_DEFAULTS, validSelection } from '../src/modelSettings.js';

const stream = (parts) => new ReadableStream({ start(controller) {
  for (const part of parts) controller.enqueue(part);
  controller.close();
} });
const encode = (text) => new TextEncoder().encode(text);

test('SSE preserves every byte boundary including UTF-8 and CRLF', async () => {
  const bytes = encode('data: {"type":"stage1_complete","data":"café"}\r\n\r\ndata: {"type":"complete"}\n\n');
  const events = [];
  await readEventStream(stream(Array.from(bytes, (byte) => new Uint8Array([byte]))), (type, event) => events.push([type, event.data]));
  assert.deepEqual(events, [['stage1_complete', 'café'], ['complete', undefined]]);
});

test('SSE rejects server errors and incomplete streams', async () => {
  await assert.rejects(readEventStream(stream([encode('data: {"type":"error","message":"Insufficient credits"}\n\n')]), () => {}), /Insufficient credits/);
  await assert.rejects(readEventStream(stream([encode('data: {"type":"stage1_start"}\n\n')]), () => {}), /before the council finished/);
});

test('SSE handles completion without final newline', async () => {
  const types = [];
  await readEventStream(stream([encode('data: {"type":"complete"}')]), (type) => types.push(type));
  assert.deepEqual(types, ['complete']);
});

test('both message APIs transmit selected council and chairman', async (t) => {
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push(JSON.parse(options.body));
    return url.endsWith('/stream') ? new Response('data: {"type":"complete"}\n\n') : Response.json({});
  });
  await api.sendMessage('123', 'question', FALLBACK_DEFAULTS);
  await api.sendMessageStream('123', 'question', () => {}, FALLBACK_DEFAULTS);
  assert.deepEqual(requests, Array(2).fill({ content: 'question', ...FALLBACK_DEFAULTS }));
});

test('HTTP validation and connection errors are actionable', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: [{ msg: 'Select a valid model' }] }, { status: 422 }));
  await assert.rejects(api.listModels(), /Select a valid model/);
  mock.mock.mockImplementation(async () => { throw new TypeError('network'); });
  await assert.rejects(api.listModels(), /backend is running on port 8001/);
});

test('selection guards reject empty, duplicate, malformed and oversized councils', () => {
  assert.equal(validSelection(FALLBACK_DEFAULTS), true);
  for (const council_models of [[], ['a/b', 'a/b'], ['bad'], Array.from({ length: 27 }, (_, i) => `a/${i}`)]) {
    assert.equal(validSelection({ ...FALLBACK_DEFAULTS, council_models }), false);
  }
  assert.equal(validSelection({ ...FALLBACK_DEFAULTS, chairman_model: '' }), false);
  assert.equal(validSelection({ ...FALLBACK_DEFAULTS, chairman_model: FALLBACK_DEFAULTS.council_models[0] }), false);
  assert.equal(validSelection({ council_models: ['provider/model:free'], chairman_model: 'provider/model' }), false);
  assert.equal(validSelection({ council_models: ['provider/model'], chairman_model: 'provider/model:online' }), false);
  assert.equal(validSelection({ council_models: ['deepseek/example:free'], chairman_model: 'other/chair' }), true);
});


test('default council includes all seven requested judges with a separate chairman', () => {
  assert.deepEqual(FALLBACK_DEFAULTS.council_models, [
    'openai/gpt-6.1-sol', 'google/gemini-4-argon', 'anthropic/claude-sonnet-5.5', 'x-ai/grok-4.7',
    'moonshotai/kimi-k3.1-pro', 'deepseek/deepseek-v4.1-flash', 'qwen/qwen3.8-max-0902',
  ]);
  assert.equal(FALLBACK_DEFAULTS.chairman_model, 'anthropic/claude-opus-5.5');
  assert.equal(validSelection(FALLBACK_DEFAULTS), true);
});
