import test from 'node:test';
import assert from 'node:assert/strict';
import { FALLBACK_DEFAULTS, resetSelection } from '../src/modelSettings.js';
import { safeCitationUrl, safeCitations, researchWarnings } from '../src/research.js';
import { api } from '../src/api.js';

test('research is off initially and resetting any configured defaults turns it off', () => {
  assert.equal(FALLBACK_DEFAULTS.research, false);
  const defaults = { council_models: ['provider/model'], chairman_model: 'provider/chair', research: true };
  const result = resetSelection(defaults);
  assert.equal(result.research, false);
  assert.notEqual(result.council_models, defaults.council_models);
  assert.deepEqual(result.council_models, defaults.council_models);
  assert.equal(defaults.research, true);
});

test('both message APIs send explicit boolean research choices', async (t) => {
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push(JSON.parse(options.body));
    return url.endsWith('/stream') ? new Response('data: {"type":"complete"}\n\n') : Response.json({});
  });
  for (const options of [{}, { research: true }, { research: false }, { research: 'true' }]) {
    await api.sendMessage('123', 'question', options);
    await api.sendMessageStream('123', 'question', () => {}, options);
  }
  assert.deepEqual(requests.map((request) => request.research), [false, false, true, true, false, false, false, false]);
});

test('citation URLs allow only public-domain HTTP(S) links without credentials', () => {
  assert.equal(safeCitationUrl('https://example.com/article?q=one#source'), 'https://example.com/article?q=one#source');
  assert.equal(safeCitationUrl('http://www.example.com/'), 'http://www.example.com/');
  for (const url of [
    'javascript:alert(1)', 'data:text/html,hello', '//example.com/a', '/relative',
    'https://user:secret@example.com/', 'https://localhost/', 'http://sub.localhost/',
    'http://printer.local/', 'http://host.internal/', 'http://intranet/',
    'http://127.0.0.1/', 'http://10.0.0.1/', 'http://169.254.169.254/', 'http://172.16.0.1/',
    'http://192.168.0.1/', 'http://2130706433/', 'http://0x7f000001/', 'http://127.1/',
    'http://[::1]/', 'http://[fc00::1]/', 'https://localhost./', ' https://example.com/',
    'https://example.com/\nsecret', '', null, {},
  ]) assert.equal(safeCitationUrl(url), null, String(url));
});

test('citation display filters unsafe values, deduplicates and bounds untrusted text', () => {
  assert.deepEqual(safeCitations(null), []);
  const results = safeCitations([
    null, 'bad', { url: 'javascript:alert(1)' },
    { url: 'https://example.com/a', title: '<script>not executed</script>', content: 'x'.repeat(3000) },
    { url: 'https://example.com/a', title: 'duplicate' },
    { url: 'https://example.com/b', title: {}, content: [] },
  ]);
  assert.equal(results.length, 2);
  assert.equal(results[0].content.length, 2000);
  assert.equal(results[0].title, '<script>not executed</script>');
  assert.equal(results[1].title, 'https://example.com/b');
  assert.equal(safeCitations(Array.from({ length: 150 }, (_, i) => ({ url: `https://example.com/${i}` }))).length, 150);
  assert.equal(safeCitations(Array.from({ length: 312 }, (_, i) => ({ url: `https://example.com/${i}` }))).length, 312);
  assert.equal(safeCitations(Array.from({ length: 400 }, (_, i) => ({ url: `https://example.com/${i}` }))).length, 312);
});

test('research warnings disclose failed and unsourced models without claiming fetch success', () => {
  assert.deepEqual(researchWarnings(undefined, 0), []);
  const research = { requested: true, warnings: ['Provider limit reached', 'Provider limit reached'], failed_models: ['provider/failed'], no_source_models: ['provider/uncited'] };
  const warnings = researchWarnings(research, 2);
  assert.equal(warnings.filter((warning) => warning === 'Provider limit reached').length, 1);
  assert.ok(warnings.some((warning) => warning.includes('provider/failed')));
  assert.ok(warnings.some((warning) => warning.includes('provider/uncited')));
  assert.equal(research.warnings.length, 2);
  assert.ok(researchWarnings({ requested: true }, 0).some((warning) => warning.includes('unverified')));
});
