/** API client. OpenRouter credentials stay on the backend. */
const API_BASE = 'http://localhost:8001';

async function checkedFetch(path, options) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error('Cannot reach the council server. Check that the backend is running on port 8001.');
  }
  if (!response.ok) {
    let detail;
    try {
      const body = await response.json();
      detail = typeof body.detail === 'string' ? body.detail :
        Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join('; ') : body.message;
    } catch { /* A proxy may return a non-JSON error. */ }
    throw new Error(detail || `Request failed (HTTP ${response.status}). Check the backend and try again.`);
  }
  return response;
}

const post = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

/** Preserve partial lines and UTF-8 characters across network chunks. */
export async function readEventStream(body, onEvent) {
  if (!body) throw new Error('The server did not return a response stream.');
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let dataLines = [];
  let completed = false;
  const dispatch = () => {
    if (!dataLines.length) return;
    const event = JSON.parse(dataLines.join('\n'));
    dataLines = [];
    if (event.type === 'error') throw new Error(event.message || 'Council request failed.');
    if (event.type === 'complete') completed = true;
    onEvent(event.type, event);
  };
  const line = (value) => {
    value = value.replace(/\r$/, '');
    if (value === '') dispatch();
    else if (value.startsWith('data:')) dataLines.push(value.slice(5).replace(/^ /, ''));
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let end;
      while ((end = buffer.indexOf('\n')) !== -1) {
        line(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
      }
      if (done) break;
    }
    if (buffer) line(buffer);
    dispatch();
    if (!completed) throw new Error('The connection ended before the council finished. Check the conversation before trying again.');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const api = {
  async listModels() {
    return (await checkedFetch('/api/models')).json();
  },
  async listConversations() {
    return (await checkedFetch('/api/conversations')).json();
  },
  async createConversation() {
    return (await checkedFetch('/api/conversations', post({}))).json();
  },
  async getConversation(id) {
    return (await checkedFetch(`/api/conversations/${id}`)).json();
  },
  async sendMessage(id, content, options = {}) {
    return (await checkedFetch(`/api/conversations/${id}/message`, post({ content, ...options }))).json();
  },
  async sendMessageStream(id, content, onEvent, options = {}) {
    const response = await checkedFetch(`/api/conversations/${id}/message/stream`, post({ content, ...options }));
    await readEventStream(response.body, onEvent);
  },
};
