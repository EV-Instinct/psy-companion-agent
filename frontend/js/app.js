/** 应用编排：会话、三种输入方式、流式渲染、弹层。 */

import { fetchHealth, fetchHistory, streamChat } from './api.js';
import * as ui from './ui.js';
import { createVoiceController } from './voice.js';
import { fileToDataUrl } from './image.js';
import { initSettings, loadConfig, hasKey } from './settings.js';

/** 只有配了自己的 Key 才下发本机配置，否则用服务端默认。 */
function localLlmConfig() {
  const cfg = loadConfig();
  return hasKey(cfg) ? cfg : undefined;
}

const $ = (id) => document.getElementById(id);

const state = {
  sessionId: loadSessionId(),
  mode: 'text',
  sending: false,
  imageDataUrl: null,
  voiceText: '',
};

let lastHealth = null;
let currentAudio = null;

function loadSessionId() {
  const key = 'shudong.session';
  let sid = localStorage.getItem(key);
  if (!sid || sid.length < 8) {
    sid = (crypto.randomUUID ? crypto.randomUUID() : `s${Date.now()}${Math.random().toString(16).slice(2)}`)
      .replace(/-/g, '')
      .slice(0, 24);
    localStorage.setItem(key, sid);
  }
  return sid;
}

init();

async function init() {
  window.__appReady = true;
  try { sessionStorage.removeItem('wb_rsc_retry'); } catch (_) { /* 忽略 */ }
  ui.setSpeakHandler((text, btn) => speak(text, btn));
  adaptPlaceholder();
  bindTabs();
  bindTextInput();
  bindChips();
  bindVoice();
  bindImage();
  bindModal();
  bindNewSession();
  initSettings({ onChange: onLlmConfigChange });
  await checkHealth();
  await restoreHistory();
  maybeShowIntro();
  updateSendState();
}

/** 顶栏状态：本机 Key 优先，否则显示服务端模式。模型名只显示最后一段，避免挤爆顶栏。 */
function shortModel(name) {
  return (name || '').split('/').pop();
}

function updateChip(health) {
  const chip = $('mode-chip');
  const cfg = loadConfig();
  const btn = $('btn-settings');
  btn.classList.toggle('is-on', hasKey(cfg));
  const narrow = window.matchMedia('(max-width: 640px)').matches;

  if (hasKey(cfg)) {
    chip.textContent = narrow ? '本机 Key' : `已连接 · ${shortModel(cfg.model) || 'AI'} · 本机 Key`;
    chip.classList.remove('is-mock');
    chip.title = `正在使用本机配置：${cfg.model || 'AI'}`;
    return;
  }
  chip.title = health ? `服务端模型：${health.model || 'AI'}` : '';
  if (health && health.mode === 'mock') {
    chip.textContent = '演示模式';
    chip.classList.add('is-mock');
  } else if (health) {
    chip.textContent = narrow ? '已连接' : `已连接 · ${shortModel(health.model) || 'AI'}`;
    chip.classList.remove('is-mock');
  }
}

function onLlmConfigChange() {
  updateChip(lastHealth);
}

/* ---------- 模式切换 ---------- */
function adaptPlaceholder() {
  const input = $('input');
  const isNarrow = window.matchMedia('(max-width: 640px)').matches;
  input.placeholder = isNarrow ? '说说现在的心情…' : '说说现在的心情…（Enter 发送，Shift+Enter 换行）';
}

function bindTabs() {
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => setMode(tab.dataset.mode));
  });
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    const active = tab.dataset.mode === mode;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  $('panel-text').hidden = mode !== 'text';
  $('panel-voice').hidden = mode !== 'voice';
  $('panel-image').hidden = mode !== 'image';
  if (mode === 'text') $('input').focus();
}

/* ---------- 文字 ---------- */
function bindTextInput() {
  const input = $('input');
  input.addEventListener('input', () => {
    autosize(input);
    updateSendState();
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendText();
    }
  });
  $('btn-send').addEventListener('click', sendText);
}

function autosize(input) {
  input.style.height = 'auto';
  input.style.height = `${Math.max(48, Math.min(input.scrollHeight, 130))}px`;
}

function updateSendState() {
  const hasText = $('input').value.trim().length > 0;
  $('btn-send').disabled = !hasText || state.sending;
}

async function sendText() {
  const input = $('input');
  const text = input.value.trim();
  if (!text || state.sending) return;
  input.value = '';
  autosize(input);
  updateSendState();
  await sendMessage({ type: 'text', content: text });
}

/* ---------- 快捷入口 ---------- */
function bindChips() {
  $('chips').addEventListener('click', (event) => {
    const chip = event.target.closest('.chip');
    if (!chip) return;
    const text = chip.dataset.text || chip.textContent;
    if (state.sending) return;
    sendMessage({ type: 'text', content: text });
  });
}

/* ---------- 核心发送 ---------- */
async function sendMessage({ type, content, imageDataUrl = null }) {
  if (state.sending) return;
  const text = (content || '').trim();
  if (!text && !imageDataUrl) return;

  state.sending = true;
  updateSendState();
  ui.hideRiskStrip();
  ui.addUserMessage(text, { type, imageUrl: type === 'image' ? imageDataUrl : null });

  const bot = ui.createBotMessage({
    onSpeak: (speakText, btn) => speak(speakText, btn),
  });  bot.setTyping(true);

  try {
    await streamChat({
      sessionId: state.sessionId,
      message: {
        type,
        content: text || '帮我看看这张图片',
        image_data_url: imageDataUrl,
        llm_config: localLlmConfig(),
      },
      onEvent: (name, data) => {
        if (name === 'delta') {
          bot.setTyping(false);
          bot.append(data.text || '');
          ui.scrollToBottom();
        } else if (name === 'risk') {
          ui.showRiskStrip(data.level, data.reasons || []);
        } else if (name === 'suggestions') {
          bot.addCards(data.cards || []);
        } else if (name === 'error') {
          bot.setTyping(false);
          bot.append(data.message || '我这边出了点小状况。');
        }
      },
    });
  } catch (err) {
    bot.setTyping(false);
    bot.append(err.message || '我这边好像断线了，过一会儿再试试？');
  } finally {
    bot.finish();
    state.sending = false;
    updateSendState();
    ui.scrollToBottom();
    // 自动朗读：设置里开启且回复有实质内容
    const cfg = loadConfig();
    if (cfg && cfg.auto_read && bot.bubble.textContent.trim().length > 4) {
      speak(bot.bubble.textContent, bot.speakBtn);
    }
  }
}

/* ---------- 语音合成（朗读回复） ---------- */
/** 朗读统一走服务端 TTS（硅基流动 CosyVoice2），不再使用浏览器/微软语音。 */
async function speak(text, btn) {
  const clean = (text || '').replace(/\s+/g, ' ').trim();
  if (!clean) return;
  await speakWithAI(clean, btn);
}

/** AI 音色朗读：提交异步任务 → 轮询 → 播放（部署网关有 15 秒上限，必须异步）。 */
async function speakWithAI(text, btn) {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  const original = btn ? btn.textContent : '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🔊 生成中…';
  }
  try {
    const res = await fetch('/api/tts/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 600), llm_config: localLlmConfig() }),
    });
    const created = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(created.detail || `朗读失败（${res.status}）`);
    const jobId = created.job_id;

    // 轮询：202=生成中，200=音频就绪，502=失败
    let audioBlob = null;
    const deadline = Date.now() + 150000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const poll = await fetch(`/api/tts/jobs/${jobId}`);
      if (poll.status === 202) continue;
      if (poll.ok) {
        audioBlob = await poll.blob();
        break;
      }
      const err = await poll.json().catch(() => ({}));
      throw new Error(err.detail || `朗读失败（${poll.status}）`);
    }
    if (!audioBlob) throw new Error('朗读超时，请稍后再试');

    const url = URL.createObjectURL(audioBlob);
    const audio = new Audio(url);
    currentAudio = audio;
    let aiRestored = false;
    const restoreAI = () => {
      if (aiRestored) return;
      aiRestored = true;
      if (btn) {
        btn.disabled = false;
        btn.textContent = original || '🔊 朗读';
      }
    };
    audio.onended = () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
      restoreAI();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
      restoreAI();
    };
    // 保险必须早于 play() 注册：无音频设备环境 play() 可能挂起
    const duration = audio.duration && isFinite(audio.duration) ? audio.duration * 1000 : 60000;
    setTimeout(restoreAI, duration + 8000);
    audio.play().catch(() => { /* 自动播放被拦截：按钮由保险恢复 */ });
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔊 朗读失败';
      btn.title = `朗读失败：${err.message || '模型繁忙，请稍后再试'}`;
      setTimeout(() => { btn.textContent = original || '🔊 朗读'; }, 3000);
    }
  }
}

/* ---------- 语音 ---------- */
function bindVoice() {
  const btn = $('btn-voice');
  const hint = $('voice-hint');
  const transcript = $('voice-transcript');
  const actions = $('voice-actions');
  let recording = false;

  const controller = createVoiceController({
    getConfig: () => localLlmConfig(),
    onStart() {
      recording = true;
      btn.classList.add('is-recording');
      hint.textContent = '正在录音…说完松开';
      transcript.hidden = true;
      actions.hidden = true;
      transcript.contentEditable = 'false';
    },
    onTranscribing() {
      recording = false;
      btn.classList.remove('is-recording');
      hint.textContent = '正在识别…';
    },
    onFinal(text) {
      recording = false;
      btn.classList.remove('is-recording');
      if (text) {
        state.voiceText = text;
        transcript.hidden = false;
        transcript.textContent = text;
        transcript.contentEditable = 'true';
        actions.hidden = false;
        hint.textContent = '可以改一下错字，再发送';
      } else {
        hint.textContent = '没有听清，按住再说一次吧';
      }
    },
    onEnd() {
      recording = false;
      btn.classList.remove('is-recording');
    },
    onError(code) {
      recording = false;
      btn.classList.remove('is-recording');
      const map = {
        'not-allowed': '没有麦克风权限，请在浏览器设置里允许后重试',
        'no-speech': '没有录到声音，按住再说一次吧',
        'audio-capture': '没有找到麦克风，检查一下设备',
      };
      hint.textContent = map[code] || `语音识别失败：${code === 'asr-failed' ? '网络或模型繁忙，可以改用文字输入' : '请重试'}`;
    },
  });

  if (!controller.supported) {
    $('voice-fallback').hidden = false;
    btn.disabled = true;
    btn.style.opacity = '0.5';
    hint.hidden = true;
    return;
  }

  const start = (event) => {
    event.preventDefault();
    if (state.sending || recording) return;
    try { btn.setPointerCapture(event.pointerId); } catch (_) { /* ignore */ }
    controller.start();
  };
  const stop = () => {
    if (!recording) return;
    controller.stop();
  };

  btn.addEventListener('pointerdown', start);
  btn.addEventListener('pointerup', stop);
  btn.addEventListener('pointercancel', stop);
  btn.addEventListener('pointerleave', stop);

  $('btn-voice-cancel').addEventListener('click', () => {
    state.voiceText = '';
    transcript.hidden = true;
    transcript.textContent = '';
    transcript.contentEditable = 'false';
    actions.hidden = true;
    hint.textContent = '按住下面的按钮说话，说完松开';
  });

  $('btn-voice-send').addEventListener('click', () => {
    const text = (transcript.innerText || '').trim();
    if (!text) return;
    actions.hidden = true;
    transcript.hidden = true;
    transcript.textContent = '';
    transcript.contentEditable = 'false';
    hint.textContent = '按住下面的按钮说话，说完松开';
    sendMessage({ type: 'voice', content: text });
  });
}

/* ---------- 图片 ---------- */
function bindImage() {
  const dropzone = $('dropzone');
  const fileInput = $('file-input');
  const preview = $('image-preview');
  const thumb = $('image-thumb');
  const tip = document.querySelector('.panel-tip');

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    fileInput.value = '';
    if (!file) return;
    try {
      const { dataUrl } = await fileToDataUrl(file);
      state.imageDataUrl = dataUrl;
      thumb.src = dataUrl;
      dropzone.hidden = true;
      preview.hidden = false;
      tip.textContent = '小提示：图片里如果有姓名、学校、住址，建议先遮住再发。';
    } catch (err) {
      tip.textContent = err.message || '这张图片读不出来，换一张试试';
    }
  });

  $('btn-image-remove').addEventListener('click', resetImage);
  $('btn-image-send').addEventListener('click', async () => {
    if (!state.imageDataUrl) return;
    const caption = $('image-caption').value.trim();
    const dataUrl = state.imageDataUrl;
    resetImage();
    await sendMessage({ type: 'image', content: caption || '帮我看看这张图片', imageDataUrl: dataUrl });
  });
}

function resetImage() {
  state.imageDataUrl = null;
  $('image-thumb').src = '';
  $('image-preview').hidden = true;
  $('dropzone').hidden = false;
  $('image-caption').value = '';
  document.querySelector('.panel-tip').textContent = '小提示：图片里如果有姓名、学校、住址，建议先遮住再发。';
}

/* ---------- 弹层 ---------- */
function bindModal() {
  $('btn-intro').addEventListener('click', () => { $('intro-modal').hidden = false; });
  $('btn-intro-ok').addEventListener('click', () => {
    $('intro-modal').hidden = true;
    localStorage.setItem('shudong.intro', '1');
  });
  $('intro-modal').addEventListener('click', (event) => {
    if (event.target === $('intro-modal')) $('intro-modal').hidden = true;
  });
}

function maybeShowIntro() {
  if (!localStorage.getItem('shudong.intro')) {
    $('intro-modal').hidden = false;
  }
}

/* ---------- 会话 ---------- */
function bindNewSession() {
  $('btn-new').addEventListener('click', () => {
    localStorage.removeItem('shudong.session');
    state.sessionId = loadSessionId();
    state.imageDataUrl = null;
    state.voiceText = '';
    ui.clearChat();
    resetImage();
    $('input').value = '';
    autosize($('input'));
    updateSendState();
    setMode('text');
  });
}

async function restoreHistory() {
  try {
    const data = await fetchHistory(state.sessionId);
    const messages = (data && data.messages) || [];
    if (!messages.length) return;
    ui.hideWelcome();
    for (const message of messages) {
      if (message.role === 'user') ui.addUserMessage(message.content);
      else if (message.role === 'assistant') ui.addBotText(message.content);
    }
    ui.scrollToBottom(false);
  } catch (_) { /* 历史恢复失败不影响新对话 */ }
}

async function checkHealth() {
  try {
    lastHealth = await fetchHealth();
    updateChip(lastHealth);
    try { sessionStorage.removeItem('wb_api_retry'); } catch (_) { /* 忽略 */ }
  } catch (_) {
    const chip = $('mode-chip');
    chip.textContent = '离线';
    chip.classList.add('is-mock');
    // 分享网关缓存 HTML 时不带鉴权 cookie，接口会 403：带缓存击穿参数重载一次
    try {
      if (!sessionStorage.getItem('wb_api_retry')) {
        sessionStorage.setItem('wb_api_retry', '1');
        const url = new URL(window.location.href);
        url.searchParams.set('_t', String(Date.now()));
        window.location.replace(url.toString());
      }
    } catch (_) { /* 隐私模式忽略 */ }
  }
}
