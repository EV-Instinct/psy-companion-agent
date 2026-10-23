/** API 客户端：SSE 流式对话 + 历史 + 健康检查。 */

export async function fetchHealth() {
  const res = await fetch('/api/health', { cache: 'no-store' });
  if (!res.ok) throw new Error('health failed');
  return res.json();
}

export async function fetchHistory(sessionId) {
  const res = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`, { cache: 'no-store' });
  if (!res.ok) return { messages: [] };
  return res.json();
}

/**
 * 发起流式对话。onEvent(name, data) 按 SSE 事件逐个回调。
 */
export async function streamChat({ sessionId, message, onEvent, signal }) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  });

  if (!res.ok) {
    let detail = '网络出了点问题，稍后再试。';
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed.name, parsed.data);
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function parseBlock(block) {
  const lines = block.split('\n').filter((line) => line.trim());
  if (!lines.length) return null;
  let name = 'message';
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith('event:')) name = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  let data = {};
  if (dataLines.length) {
    try { data = JSON.parse(dataLines.join('\n')); } catch (_) { data = {}; }
  }
  return { name, data };
}
