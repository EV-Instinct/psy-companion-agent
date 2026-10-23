/** 界面渲染：消息气泡、资源卡片、风险提示。 */

const chatEl = document.getElementById('chat');
const welcomeEl = document.getElementById('welcome');
const riskEl = document.getElementById('risk-strip');

let speakHandler = null;

/** 注册朗读回调（由 app.js 注入），历史恢复的消息也能用。 */
export function setSpeakHandler(fn) {
  speakHandler = fn;
}

const BOT_AVATAR = `
<svg viewBox="0 0 40 40" width="22" height="22" fill="none" aria-hidden="true">
  <path d="M20 34V19" stroke="#2E9B8C" stroke-width="2.6" stroke-linecap="round"/>
  <path d="M20 22c-6 0-9-3.4-9-8 0-3 2-5.5 5-6.5 1.2-2.6 3.6-4 6.5-4 4 0 6.8 2.6 7.2 6.3 2.6 1 4.3 3.3 4.3 6.1 0 3.9-3.2 6.1-7 6.1h-7z" fill="#CDEAE4"/>
  <circle cx="16" cy="14" r="1.7" fill="#2E9B8C"/>
  <circle cx="24" cy="14" r="1.7" fill="#2E9B8C"/>
  <path d="M17 17.4c1.8 1.6 4.4 1.6 6.2 0" stroke="#2E9B8C" stroke-width="1.6" stroke-linecap="round"/>
</svg>`;

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function hideWelcome() {
  if (welcomeEl) welcomeEl.style.display = 'none';
}

export function scrollToBottom(smooth = true) {
  chatEl.scrollTo({ top: chatEl.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
}

export function addUserMessage(text, { type = 'text', imageUrl = null } = {}) {
  hideWelcome();
  const msg = el('div', 'msg user');
  const avatar = el('div', 'avatar', '我');
  const body = el('div', 'msg-body');

  if (type !== 'text') {
    body.appendChild(el('div', 'msg-tag', type === 'voice' ? '语音转文字' : '图片'));
  }
  if (imageUrl) {
    const img = document.createElement('img');
    img.className = 'msg-image';
    img.src = imageUrl;
    img.alt = '我发送的图片';
    body.appendChild(img);
  }
  if (text) {
    body.appendChild(el('div', 'bubble', text));
  }
  msg.append(avatar, body);
  chatEl.appendChild(msg);
  scrollToBottom();
  return msg;
}

export function addBotText(text) {
  const bot = createBotMessage();
  bot.append(text);
  bot.finish();
  return bot;
}

export function createBotMessage({ onSpeak } = {}) {
  hideWelcome();
  const root = el('div', 'msg bot');
  const avatar = el('div', 'avatar');
  avatar.innerHTML = BOT_AVATAR;
  const body = el('div', 'msg-body');
  const bubble = el('div', 'bubble');
  const typing = el('div', 'typing');
  typing.append(el('span'), el('span'), el('span'));
  bubble.appendChild(typing);
  bubble.dataset.state = 'typing';
  body.appendChild(bubble);

  const speakBtn = el('button', 'speak-btn', '🔊 朗读');
  speakBtn.type = 'button';
  speakBtn.title = '把小树的话读出来';
  speakBtn.hidden = true;
  speakBtn.addEventListener('click', () => {
    const handler = speakHandler || onSpeak;
    if (handler) handler(bubble.textContent, speakBtn);
  });
  body.appendChild(speakBtn);

  root.append(avatar, body);
  chatEl.appendChild(root);
  scrollToBottom();
  return new BotMessage(root, body, bubble, speakBtn);
}

class BotMessage {
  constructor(root, body, bubble, speakBtn) {
    this.root = root;
    this.body = body;
    this.bubble = bubble;
    this.speakBtn = speakBtn;
    this.done = false;
  }

  setTyping(on) {
    if (on) {
      if (this.bubble.dataset.state !== 'typing') {
        this.bubble.textContent = '';
        const typing = el('div', 'typing');
        typing.append(el('span'), el('span'), el('span'));
        this.bubble.appendChild(typing);
        this.bubble.dataset.state = 'typing';
      }
    } else if (this.bubble.dataset.state === 'typing') {
      this.bubble.textContent = '';
      this.bubble.dataset.state = 'text';
      this.bubble.classList.add('streaming');
    }
  }

  append(text) {
    if (!text) return;
    if (this.bubble.dataset.state !== 'text') {
      this.bubble.textContent = '';
      this.bubble.dataset.state = 'text';
      this.bubble.classList.add('streaming');
    }
    this.bubble.textContent += text;
  }

  addCards(cards) {
    if (!cards || !cards.length) return;
    const wrap = el('div', 'cards');
    for (const card of cards) {
      wrap.appendChild(renderCard(card));
    }
    this.body.appendChild(wrap);
    scrollToBottom();
  }

  finish() {
    if (this.done) return;
    this.done = true;
    this.bubble.classList.remove('streaming');
    if (this.bubble.dataset.state === 'typing') {
      this.bubble.textContent = '我在听着，你慢慢说。';
      this.bubble.dataset.state = 'text';
    }
    // 有实质内容才显示朗读按钮
    if (this.speakBtn && this.bubble.textContent.trim().length > 4) {
      this.speakBtn.hidden = false;
    }
  }
}

function renderCard(card) {
  const isHotline = card.kind === 'hotline';
  const wrap = el('div', `res-card${isHotline ? ' hotline' : ''}`);
  const info = el('div');
  info.appendChild(el('p', 'res-title', card.title || ''));
  if (card.detail) info.appendChild(el('p', 'res-detail', card.detail));
  wrap.appendChild(info);

  if (isHotline) {
    const phone = (card.title || '').match(/\d{5}/);
    const link = document.createElement('a');
    link.className = 'res-action';
    link.textContent = card.action_text || '拨打电话';
    link.href = phone ? `tel:${phone[0]}` : '#';
    wrap.appendChild(link);
  } else {
    const btn = el('button', 'res-action', card.action_text || '知道了');
    btn.type = 'button';
    btn.addEventListener('click', () => {
      wrap.style.opacity = '0.55';
      btn.disabled = true;
      btn.textContent = '已了解';
    });
    wrap.appendChild(btn);
  }
  return wrap;
}

export function showRiskStrip(level, reasons = []) {
  if (level === 'green') return;
  const isRed = level === 'red';
  riskEl.hidden = false;
  riskEl.classList.toggle('is-red', isRed);
  if (isRed) {
    riskEl.textContent = '现在最重要的是你的安全：先待在有人的地方，把这段话给信任的大人看；紧急情况请拨 110 / 120。';
  } else {
    const reason = reasons.length ? `（${reasons.join('、')}）` : '';
    riskEl.textContent = `小树注意到你现在不太好受${reason}。如果这种难受持续很久，可以告诉信任的大人，或拨打 12356。`;
    window.clearTimeout(showRiskStrip._timer);
    showRiskStrip._timer = window.setTimeout(() => { riskEl.hidden = true; }, 12000);
  }
}

export function hideRiskStrip() {
  riskEl.hidden = true;
}

export function clearChat() {
  chatEl.querySelectorAll('.msg').forEach((node) => node.remove());
  riskEl.hidden = true;
  if (welcomeEl) welcomeEl.style.display = '';
  chatEl.scrollTop = 0;
}
