// Fetch wrappers + the SSE-over-POST stream reader for /api/chat.

async function json(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).error || detail; } catch { /* not json */ }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  health: () => json('GET', '/api/health'),
  onboardingStatus: () => json('GET', '/api/onboarding/status'),
  onboardingComplete: (body) => json('POST', '/api/onboarding/complete', body),
  messages: (beforeId) =>
    json('GET', beforeId ? `/api/messages?before_id=${beforeId}` : '/api/messages'),
  catchup: () => json('POST', '/api/catchup'),
  settings: () => json('GET', '/api/settings'),
  saveSettings: (s) => json('PUT', '/api/settings', s),
  models: () => json('GET', '/api/models'),
  testConnection: (kind, url) => json('POST', '/api/settings/test-connection', { kind, url }),
  facts: () => json('GET', '/api/memory/facts'),
  deleteFact: (id) => json('DELETE', `/api/memory/facts/${id}`),
  manifest: () => json('GET', '/api/photos/manifest'),
  generatePhoto: (mood) => json('POST', '/api/photos/generate', { mood }),
  wipe: () => json('POST', '/api/data/wipe', { confirm: 'DELETE' }),

  async uploadPhoto(file) {
    const form = new FormData();
    form.append('file', file);
    const r = await fetch('/api/uploads/photo', { method: 'POST', body: form });
    if (!r.ok) throw new Error('upload failed');
    return r.json();
  },

  // POST /api/chat and dispatch SSE events to handlers: {token, status, photo, done, error}
  async chatStream(body, handlers) {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok || !r.body) throw new Error('chat request failed');
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = 'message';
        let data = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (data && handlers[event]) handlers[event](JSON.parse(data));
      }
    }
  },
};
