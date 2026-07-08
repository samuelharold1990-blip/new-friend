// Chat view: bubbles, day separators, streaming, typing indicator, photos.

import { api } from './api.js';
import { store } from './store.js';
import { buildComposer } from './composer.js';

const CHARS_PER_TICK = 1.4; // ~35 chars/s when realistic typing is on
const TICK_MS = 40;

let listEl = null;
let typingEl = null;
let liveBubble = null; // { el, bubbleEl, target, shown, timer, doneData }

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}
function fmtDay(ts) {
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(Date.now() - 864e5);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function photoEl(path) {
  const img = el('img');
  img.src = '/' + path;
  img.loading = 'lazy';
  img.alt = 'photo';
  img.addEventListener('click', () => {
    const lb = document.getElementById('lightbox');
    document.getElementById('lightbox-img').src = img.src;
    lb.classList.remove('hidden');
  });
  return img;
}

function messageEl(msg, prev) {
  const mine = msg.role === 'user';
  const wrap = el('div', `msg ${mine ? 'me' : 'them'}`);
  if (!prev || prev.role !== msg.role || msg.created_at - prev.created_at > 3 * 60000) {
    wrap.classList.add('gap');
  }
  if (msg.photo_path) {
    const b = el('div', 'bubble photo');
    b.appendChild(photoEl(msg.photo_path));
    wrap.appendChild(b);
  }
  if (msg.content) {
    wrap.appendChild(el('div', 'bubble', msg.content));
  }
  const showTime = !prev || msg.created_at - prev.created_at > 10 * 60000;
  if (showTime) wrap.appendChild(el('div', 'time', fmtTime(msg.created_at)));
  return wrap;
}

function renderAll() {
  listEl.textContent = '';
  let prev = null;
  for (const msg of store.messages) {
    if (!prev || fmtDay(prev.created_at) !== fmtDay(msg.created_at)) {
      listEl.appendChild(el('div', 'day-sep', fmtDay(msg.created_at)));
    }
    if (store.firstProactiveId && msg.id === store.firstProactiveId) {
      listEl.appendChild(el('div', 'unread-sep', 'while you were away'));
    }
    listEl.appendChild(messageEl(msg, prev));
    prev = msg;
  }
  scrollToBottom();
}

function scrollToBottom() {
  listEl.scrollTop = listEl.scrollHeight;
}

function showTyping() {
  hideTyping();
  typingEl = el('div', 'msg them gap');
  const t = el('div', 'bubble typing');
  t.append(el('span'), el('span'), el('span'));
  typingEl.appendChild(t);
  listEl.appendChild(typingEl);
  scrollToBottom();
}
function hideTyping() {
  typingEl?.remove();
  typingEl = null;
}

function startLiveBubble(realistic) {
  hideTyping();
  const wrap = el('div', 'msg them gap');
  const bubble = el('div', 'bubble', '');
  wrap.appendChild(bubble);
  listEl.appendChild(wrap);
  liveBubble = { el: wrap, bubbleEl: bubble, target: '', shown: 0, timer: null, doneData: null };
  if (realistic) {
    liveBubble.timer = setInterval(() => {
      if (!liveBubble) return;
      if (liveBubble.shown < liveBubble.target.length) {
        liveBubble.shown = Math.min(liveBubble.target.length, liveBubble.shown + CHARS_PER_TICK);
        liveBubble.bubbleEl.textContent = liveBubble.target.slice(0, Math.floor(liveBubble.shown));
        scrollToBottom();
      } else if (liveBubble.doneData) {
        finalizeLive();
      }
    }, TICK_MS);
  }
}

function pushLiveText(text, realistic) {
  if (!liveBubble) startLiveBubble(realistic);
  liveBubble.target += text;
  if (!realistic) {
    liveBubble.shown = liveBubble.target.length;
    liveBubble.bubbleEl.textContent = liveBubble.target;
    scrollToBottom();
  }
}

function finalizeLive() {
  if (!liveBubble) return;
  clearInterval(liveBubble.timer);
  const data = liveBubble.doneData;
  liveBubble.el.remove();
  liveBubble = null;
  if (data) {
    // replace the optimistic user bubble + live bubble with canonical messages
    if (data.user_message) upsertMessage(data.user_message);
    if (data.reply) upsertMessage(data.reply);
    renderAll();
  }
}

function upsertMessage(msg) {
  if (!store.messages.some((m) => m.id === msg.id)) store.messages.push(msg);
}

async function send(text, uploadId) {
  if (store.sending) return;
  store.sending = true;
  store.emit('sending', true);
  const realistic = store.settings?.realistic_typing ?? true;

  // optimistic user bubble
  const temp = {
    id: `tmp-${Date.now()}`, role: 'user', content: text,
    photo_path: uploadId ? `uploads/${uploadId}` : null, created_at: Date.now(),
  };
  const prev = store.messages[store.messages.length - 1];
  listEl.appendChild(messageEl(temp, prev));
  scrollToBottom();

  const typingDelay = realistic ? 800 + Math.random() * 1200 : 0;
  const typingTimer = setTimeout(showTyping, typingDelay);

  try {
    await api.chatStream({ text, upload_id: uploadId || null }, {
      token: (d) => {
        clearTimeout(typingTimer);
        pushLiveText(d.text, realistic);
      },
      status: (d) => {
        if (d.state === 'taking_photo' && liveBubble) {
          liveBubble.el.appendChild(el('div', 'caption', 'taking a photo for you…'));
          scrollToBottom();
        }
      },
      photo: () => {}, // the done event carries the canonical message incl. photo
      done: (d) => {
        clearTimeout(typingTimer);
        if (liveBubble) {
          liveBubble.doneData = d;
          if (!realistic || liveBubble.shown >= liveBubble.target.length) finalizeLive();
        } else {
          hideTyping();
          if (d.user_message) upsertMessage(d.user_message);
          if (d.reply) upsertMessage(d.reply);
          renderAll();
        }
      },
      error: (d) => {
        clearTimeout(typingTimer);
        hideTyping();
        if (liveBubble) { clearInterval(liveBubble.timer); liveBubble.el.remove(); liveBubble = null; }
        const note = el('div', 'system-note', d.message + ' ');
        const retry = el('button', '', 'Retry');
        retry.addEventListener('click', () => { note.remove(); send(text, uploadId); });
        note.appendChild(retry);
        listEl.appendChild(note);
        scrollToBottom();
      },
    });
  } catch (err) {
    clearTimeout(typingTimer);
    hideTyping();
    const note = el('div', 'system-note', `Couldn't send — is the server running? (${err.message})`);
    listEl.appendChild(note);
  } finally {
    store.sending = false;
    store.emit('sending', false);
  }
}

async function loadOlder() {
  if (!store.oldestId) return;
  const { messages } = await api.messages(store.oldestId);
  if (!messages.length) { store.oldestId = null; return; }
  const keepHeight = listEl.scrollHeight - listEl.scrollTop;
  store.messages = [...messages, ...store.messages];
  store.oldestId = messages[0].id;
  renderAll();
  listEl.scrollTop = listEl.scrollHeight - keepHeight;
}

export async function renderChat(root) {
  const name = store.settings?.character?.name || 'Companion';
  root.textContent = '';

  const header = el('div', 'chat-header');
  const avatar = el('div', 'avatar', name[0].toUpperCase());
  const who = el('div', 'who');
  who.appendChild(el('div', 'name', name));
  const status = el('div', 'status',
    store.health?.mock_mode ? 'mock mode (no Ollama)' : 'local · private');
  who.appendChild(status);
  const gear = el('button', 'icon-btn', '⚙︎');
  gear.title = 'Settings';
  gear.addEventListener('click', () => { location.hash = '#settings'; });
  header.append(avatar, who, gear);

  listEl = el('div', 'messages');
  listEl.addEventListener('scroll', () => {
    if (listEl.scrollTop < 60 && store.oldestId) loadOlder();
  });

  root.append(header, listEl, buildComposer(send));

  // catch-up first so "while you were away" texts are part of this load
  try {
    const { messages: proactive } = await api.catchup();
    if (proactive.length) store.firstProactiveId = proactive[0].id;
  } catch { /* catch-up is best-effort */ }

  const { messages } = await api.messages();
  store.messages = messages;
  store.oldestId = messages.length ? messages[0].id : null;
  renderAll();
}
