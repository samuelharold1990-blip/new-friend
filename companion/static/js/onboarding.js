// First-run wizard: connectivity → model → character → done.

import { api } from './api.js';
import { store } from './store.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function field(labelText, input) {
  const f = el('div', 'field');
  f.append(el('label', '', labelText), input);
  return f;
}

function textInput(value, placeholder = '') {
  const i = el('input');
  i.type = 'text';
  i.value = value ?? '';
  i.placeholder = placeholder;
  return i;
}

function textArea(value) {
  const t = el('textarea');
  t.value = value ?? '';
  return t;
}

const state = { step: 0, model: null, models: [] };

export async function renderOnboarding(root) {
  root.textContent = '';
  const panel = el('div', 'panel onboard');
  root.appendChild(panel);

  const steps = el('div', 'steps');
  for (let i = 0; i < 3; i++) steps.appendChild(el('i', i <= state.step ? 'on' : ''));

  panel.appendChild(el('div', 'logo', '💬'));

  if (state.step === 0) {
    panel.appendChild(el('h1', '', 'Welcome'));
    panel.appendChild(el('div', 'sub', 'A companion that lives entirely on your computer.'));
    panel.appendChild(steps);
    const card = el('div', 'card');
    card.appendChild(el('div', 'lbl', 'Checking your local AI…'));
    const status = el('div', 'hint', 'looking for Ollama…');
    card.appendChild(status);
    panel.appendChild(card);

    const check = async () => {
      try {
        const s = await api.onboardingStatus();
        if (s.ollama_reachable && s.models.length) {
          state.models = s.models;
          status.innerHTML = '';
          status.appendChild(el('span', 'ok', `✓ Ollama found — ${s.models.length} model(s) installed`));
          const next = el('button', 'btn', 'Continue');
          next.style.marginTop = '12px';
          next.addEventListener('click', () => { state.step = 1; renderOnboarding(root); });
          card.appendChild(next);
        } else if (s.ollama_reachable) {
          status.className = 'hint bad';
          status.textContent = 'Ollama is running but has no models. In a terminal, run:';
          const code = el('div', 'hint');
          code.innerHTML = '<code>ollama pull llama3.1:8b</code>';
          card.appendChild(code);
          addRetry();
        } else {
          status.className = 'hint bad';
          status.textContent = `Can't reach Ollama at ${s.ollama_url}. Install it from ollama.com, then run:`;
          const code = el('div', 'hint');
          code.innerHTML = '<code>ollama pull llama3.1:8b</code>';
          card.appendChild(code);
          addRetry();
        }
      } catch {
        status.className = 'hint bad';
        status.textContent = 'Could not reach the app server.';
        addRetry();
      }
      function addRetry() {
        const retry = el('button', 'btn secondary', 'Check again');
        retry.style.marginTop = '12px';
        retry.addEventListener('click', () => renderOnboarding(root));
        card.appendChild(retry);
      }
    };
    check();
    return;
  }

  if (state.step === 1) {
    panel.appendChild(el('h1', '', 'Pick a model'));
    panel.appendChild(el('div', 'sub', 'The brain she thinks with. You can change this later.'));
    panel.appendChild(steps);
    const card = el('div', 'card');
    const select = el('select');
    for (const m of state.models.filter((m) => !m.is_vision)) {
      const opt = el('option', '', m.name);
      opt.value = m.name;
      select.appendChild(opt);
    }
    if (!select.children.length) {
      for (const m of state.models) {
        const opt = el('option', '', m.name);
        opt.value = m.name;
        select.appendChild(opt);
      }
    }
    card.appendChild(field('Chat model', select));
    const next = el('button', 'btn', 'Continue');
    next.addEventListener('click', () => {
      state.model = select.value;
      state.step = 2;
      renderOnboarding(root);
    });
    card.appendChild(next);
    panel.appendChild(card);
    return;
  }

  // step 2: character + your name
  panel.appendChild(el('h1', '', 'Meet her'));
  panel.appendChild(el('div', 'sub', 'Shape who she is — or keep the defaults and dive in.'));
  panel.appendChild(steps);
  const card = el('div', 'card');
  const defaults = store.settings?.character || {};
  const cName = textInput(defaults.name || 'Mira');
  const cPers = textArea(defaults.personality
    || 'warm, playful and a little witty; genuinely curious about your day; loves cozy mornings, indie music, photography and long walks');
  const cApp = textArea(defaults.appearance
    || 'a woman in her mid twenties with long wavy chestnut hair, hazel eyes, a soft smile and a casual relaxed style');
  const uName = textInput('', 'what should she call you?');
  card.appendChild(field('Her name', cName));
  card.appendChild(field('Her personality', cPers));
  card.appendChild(field('Her look', cApp));
  card.appendChild(field('Your name', uName));

  const start = el('button', 'btn', 'Start chatting');
  const note = el('div', 'hint');
  start.addEventListener('click', async () => {
    start.disabled = true;
    note.textContent = 'she’s typing her first message…';
    try {
      await api.onboardingComplete({
        model: state.model,
        user_name: uName.value.trim(),
        character: {
          name: cName.value.trim() || 'Mira',
          personality: cPers.value.trim(),
          appearance: cApp.value.trim(),
        },
      });
      store.settings = await api.settings();
      location.hash = '#chat';
    } catch (e) {
      start.disabled = false;
      note.className = 'hint bad';
      note.textContent = `Something went wrong: ${e.message}`;
    }
  });
  card.appendChild(start);
  card.appendChild(note);
  panel.appendChild(card);
}
