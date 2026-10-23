/** 语音输入：录音后交给服务端识别（硅基流动 Qwen3-ASR），不再使用浏览器/微软识别引擎。 */

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];

function pickMime() {
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('读取录音失败'));
    reader.readAsDataURL(blob);
  });
}

export function createVoiceController({ onStart, onTranscribing, onFinal, onEnd, onError, getConfig }) {
  const supported = Boolean(
    navigator.mediaDevices
    && typeof navigator.mediaDevices.getUserMedia === 'function'
    && typeof window.MediaRecorder === 'function',
  );
  if (!supported) {
    return {
      supported: false,
      start() {},
      stop() {},
      abort() {},
      get active() { return false; },
    };
  }

  let recorder = null;
  let stream = null;
  let chunks = [];
  let active = false;
  let cancelled = false;

  const releaseMic = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  };

  async function upload(blob) {
    onTranscribing && onTranscribing();
    try {
      const audio = await blobToDataUrl(blob);
      const cfg = typeof getConfig === 'function' ? getConfig() : null;
      const res = await fetch('/api/asr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio, llm_config: cfg || undefined }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `识别失败（${res.status}）`);
      onFinal && onFinal((body.text || '').trim());
    } catch (err) {
      onError && onError('asr-failed', err.message || '识别失败');
    } finally {
      onEnd && onEnd();
    }
  }

  return {
    supported: true,
    async start() {
      if (active) return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        onError && onError('not-allowed', err.message);
        return;
      }
      const mime = pickMime();
      chunks = [];
      cancelled = false;
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => {
        const type = recorder && recorder.mimeType ? recorder.mimeType : mime || 'audio/webm';
        const blob = new Blob(chunks, { type });
        chunks = [];
        releaseMic();
        recorder = null;
        active = false;
        if (cancelled) {
          onEnd && onEnd();
          return;
        }
        if (!blob.size) {
          onError && onError('no-speech', '没有录到声音');
          onEnd && onEnd();
          return;
        }
        upload(blob);
      };
      recorder.start();
      active = true;
      onStart && onStart();
    },
    stop() {
      if (!active || !recorder) return;
      try { recorder.stop(); } catch (_) { /* ignore */ }
    },
    abort() {
      cancelled = true;
      if (recorder) {
        try { recorder.stop(); } catch (_) { /* ignore */ }
      }
      releaseMic();
      active = false;
    },
    get active() { return active; },
  };
}
