/** 模型配置（本机 Key）：保存、预设切换、测试连接。Key 只存在浏览器 localStorage。 */

const STORAGE_KEY = 'shudong.llm';

const PRESETS = {
  zhipu: {
    label: '智谱 GLM',
    base: 'https://open.bigmodel.cn/api/paas/v4/',
    model: 'glm-5',
    vlm: 'glm-4v-plus',
    thinking: 'disabled',
    ttsModel: '',
    ttsVoice: '',
  },
  bailian: {
    label: '阿里云百炼',
    base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-flash',
    vlm: 'qwen3-vl-plus',
    thinking: 'disabled',
    ttsModel: 'qwen3-tts-flash',
    ttsVoice: 'Cherry',
  },
  siliconflow: {
    label: '硅基流动 SiliconFlow',
    base: 'https://api.siliconflow.cn/v1',
    model: 'zai-org/GLM-4.5-Air',
    vlm: 'Qwen/Qwen3-VL-8B-Instruct',
    thinking: 'off',
    ttsModel: 'FunAudioLLM/CosyVoice2-0.5B',
    ttsVoice: 'FunAudioLLM/CosyVoice2-0.5B:claire',
  },
  custom: { label: '自定义', base: '', model: '', vlm: '', thinking: 'off', ttsModel: '', ttsVoice: '' },
};

const $ = (id) => document.getElementById(id);

export function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const cfg = JSON.parse(raw);
    if (!cfg || typeof cfg !== 'object') return null;
    // 允许只保存偏好（自动朗读 / 音色），不强制填写 Key
    return cfg;
  } catch (_) {
    return null;
  }
}

/** 是否配置了自己的 Key（决定「本机 Key」模式与 llm_config 是否下发）。 */
export function hasKey(cfg) {
  return Boolean(cfg && cfg.api_key && cfg.api_key.trim());
}

export function saveConfig(cfg) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
}

export function clearConfig() {
  localStorage.removeItem(STORAGE_KEY);
}

function readForm() {
  return {
    api_key: $('cfg-key').value.trim(),
    base_url: $('cfg-base').value.trim(),
    model: $('cfg-model').value.trim(),
    vlm_model: $('cfg-vlm').value.trim(),
    thinking: $('cfg-thinking').value,
    tts_model: $('cfg-tts-model').value.trim(),
    tts_voice: $('cfg-tts-voice').value.trim(),
    auto_read: $('cfg-autoread').checked,
  };
}

function writeForm(cfg) {
  $('cfg-key').value = cfg.api_key || '';
  $('cfg-base').value = cfg.base_url || '';
  $('cfg-model').value = cfg.model || '';
  $('cfg-vlm').value = cfg.vlm_model || '';
  $('cfg-thinking').value = cfg.thinking || 'off';
  $('cfg-tts-model').value = cfg.tts_model || '';
  $('cfg-tts-voice').value = cfg.tts_voice || '';
  $('cfg-autoread').checked = Boolean(cfg.auto_read);
}

function detectPlatform(cfg) {
  const base = (cfg.base_url || '').toLowerCase();
  if (base.includes('bigmodel.cn')) return 'zhipu';
  if (base.includes('dashscope')) return 'bailian';
  if (base.includes('siliconflow')) return 'siliconflow';
  return 'custom';
}

function showStatus(text, ok) {
  const el = $('cfg-status');
  el.hidden = false;
  el.textContent = text;
  el.style.color = ok ? 'var(--teal-dark)' : 'var(--danger)';
  el.style.background = ok ? 'var(--teal-soft)' : 'var(--danger-soft)';
}

/** 初始化设置弹层；onChange 在保存/清除后回调，用于刷新顶栏状态。 */
export function initSettings({ onChange }) {
  const modal = $('settings-modal');
  const btn = $('btn-settings');

  const open = () => {
    const cfg = loadConfig() || {
      api_key: '',
      base_url: PRESETS.bailian.base,
      model: PRESETS.bailian.model,
      vlm_model: PRESETS.bailian.vlm,
      thinking: PRESETS.bailian.thinking,
      tts_model: PRESETS.bailian.ttsModel,
      tts_voice: PRESETS.bailian.ttsVoice,
      auto_read: false,
    };
    writeForm(cfg);
    $('cfg-platform').value = detectPlatform(cfg);
    $('cfg-status').hidden = true;
    modal.hidden = false;
  };
  const close = () => { modal.hidden = true; };

  btn.addEventListener('click', open);
  modal.addEventListener('click', (event) => { if (event.target === modal) close(); });

  // 平台预设：切换时填充对应默认值（保留已填 Key、自动朗读与自定义音色）
  $('cfg-platform').addEventListener('change', (event) => {
    const preset = PRESETS[event.target.value] || PRESETS.custom;
    const key = $('cfg-key').value.trim();
    const autoRead = $('cfg-autoread').checked;
    const ttsModel = $('cfg-tts-model').value.trim();
    const ttsVoice = $('cfg-tts-voice').value.trim();
    writeForm({
      api_key: key,
      base_url: preset.base,
      model: preset.model,
      vlm_model: preset.vlm,
      thinking: preset.thinking,
      tts_model: preset.ttsModel || ttsModel,
      tts_voice: preset.ttsVoice || ttsVoice,
      auto_read: autoRead,
    });
  });

  // 显示 / 隐藏 Key
  $('cfg-toggle-key').addEventListener('click', () => {
    const input = $('cfg-key');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    $('cfg-toggle-key').textContent = show ? '隐藏' : '显示';
  });

  // 测试连接：用当前表单做一次最小调用
  $('btn-cfg-test').addEventListener('click', async () => {
    const cfg = readForm();
    if (!cfg.api_key) { showStatus('请先填写 API Key', false); return; }
    const testBtn = $('btn-cfg-test');
    testBtn.disabled = true;
    testBtn.textContent = '测试中…';
    showStatus('正在连接模型…', true);
    try {
      const res = await fetch('/api/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        showStatus(`连接成功：${body.model || cfg.model} 已返回`, true);
      } else {
        showStatus(body.detail || `连接失败（${res.status}）`, false);
      }
    } catch (err) {
      showStatus(`网络错误：${err.message}`, false);
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = '测试连接';
    }
  });

  // 保存并使用：没填 Key 也能存偏好（自动朗读 / 音色），此时仍走服务端模型
  $('btn-cfg-save').addEventListener('click', () => {
    const cfg = readForm();
    if (cfg.api_key && !cfg.base_url) { showStatus('请填写接口地址', false); return; }
    saveConfig(cfg);
    close();
    if (onChange) onChange(cfg);
  });

  // 清除配置：恢复服务端默认
  $('btn-cfg-clear').addEventListener('click', () => {
    clearConfig();
    writeForm({
      api_key: '',
      base_url: PRESETS.bailian.base,
      model: PRESETS.bailian.model,
      vlm_model: PRESETS.bailian.vlm,
      thinking: PRESETS.bailian.thinking,
      tts_model: PRESETS.bailian.ttsModel,
      tts_voice: PRESETS.bailian.ttsVoice,
      auto_read: false,
    });
    close();
    if (onChange) onChange(null);
  });

  return { open, close };
}
