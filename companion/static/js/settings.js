// Settings: connection, character, memory viewer, data controls.

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
  const label = el('label', '', labelText);
  f.append(label, input);
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

function toggle(checked) {
  const i = el('input');
  i.type = 'checkbox';
  i.checked = !!checked;
  return i;
}

function switchRow(label, sub, input) {
  const row = el('div', 'switch-row');
  const left = el('div');
  left.appendChild(el('div', 'lbl', label));
  if (sub) left.appendChild(el('div', 'sub', sub));
  row.append(left, input);
  return row;
}

export async function renderSettings(root) {
  const s = await api.settings();
  root.textContent = '';
  const panel = el('div', 'panel');

  const h1 = el('h1');
  const back = el('button', 'icon-btn back', '‹ back');
  back.addEventListener('click', () => { location.hash = '#chat'; });
  h1.append(back, document.createTextNode('Settings'));
  panel.appendChild(h1);

  // ---- Connection ----
  panel.appendChild(el('h2', '', 'Connection'));
  const conn = el('div', 'card');
  const ollamaUrl = textInput(s.ollama_url, 'http://localhost:11434');
  conn.appendChild(field('Ollama URL', ollamaUrl));

  const modelSelect = el('select');
  const modelStatus = el('div', 'hint');
  async function refreshModels() {
    modelSelect.textContent = '';
    try {
      const { models, error } = await api.models();
      if (error || !models.length) throw new Error(error || 'no models');
      for (const m of models) {
        const opt = el('option', '', m.name + (m.is_vision ? ' (vision)' : ''));
        opt.value = m.name;
        modelSelect.appendChild(opt);
      }
      modelSelect.value = models.some((m) => m.name === s.model) ? s.model : models[0].name;
      modelStatus.textContent = '';
    } catch {
      const opt = el('option', '', s.model);
      opt.value = s.model;
      modelSelect.appendChild(opt);
      modelStatus.textContent = 'Could not list models — is Ollama running?';
    }
  }
  await refreshModels();
  conn.appendChild(field('Chat model', modelSelect));
  conn.appendChild(modelStatus);

  const testBtn = el('button', 'btn secondary', 'Test connection');
  const testResult = el('span', 'hint', '');
  testBtn.addEventListener('click', async () => {
    testResult.textContent = '…';
    const r = await api.testConnection('ollama', ollamaUrl.value);
    testResult.textContent = r.detail;
    testResult.className = r.ok ? 'ok' : 'bad';
    if (r.ok) refreshModels();
  });
  const btnRow = el('div', 'btn-row');
  btnRow.append(testBtn, testResult);
  conn.appendChild(btnRow);
  panel.appendChild(conn);

  // ---- Photos / Stable Diffusion ----
  panel.appendChild(el('h2', '', 'Her photos'));
  const sd = el('div', 'card');
  const sdEnabled = toggle(s.sd_enabled);
  sd.appendChild(switchRow('Generate photos with Stable Diffusion',
    'auto-connects when a local A1111 or ComfyUI server is found; otherwise the photo pack is used', sdEnabled));
  if (store.health?.sd?.enabled && store.health?.sd?.reachable) {
    const note = el('div', 'hint ok',
      `✓ connected to ${store.health.sd.backend} — ${store.health.sd.checkpoint || 'server default model'}`
      + (store.health.sd.reference_photos
        ? ` · ${store.health.sd.reference_photos} reference photo(s)` : ''));
    sd.appendChild(note);
  }
  const sdBackend = el('select');
  for (const [v, l] of [['a1111', 'AUTOMATIC1111'], ['comfyui', 'ComfyUI']]) {
    const opt = el('option', '', l);
    opt.value = v;
    sdBackend.appendChild(opt);
  }
  sdBackend.value = s.sd_backend;
  const sdUrl = textInput(s.sd_url, 'http://localhost:7860');
  const sdRow = el('div', 'row');
  sdRow.append(field('Backend', sdBackend), field('URL', sdUrl));
  sd.appendChild(sdRow);
  const sdCheckpoint = textInput(s.sd_checkpoint, 'auto-picked — e.g. cyberrealisticPony_v90.safetensors');
  sd.appendChild(field('Checkpoint (model file)', sdCheckpoint));
  const sdPrefix = textInput(s.sd_prompt_prefix, 'auto — Pony models get score_9 tags automatically');
  sd.appendChild(field('Prompt prefix (optional)', sdPrefix));

  const sdTest = el('button', 'btn secondary', 'Generate test photo');
  const sdResult = el('div', 'hint');
  sdTest.addEventListener('click', async () => {
    sdResult.textContent = 'generating… (can take a minute)';
    try {
      const r = await api.generatePhoto('selfie_generic');
      sdResult.textContent = '';
      const img = el('img');
      img.src = r.url;
      img.style.maxWidth = '160px';
      img.style.borderRadius = '10px';
      sdResult.appendChild(img);
    } catch (e) {
      sdResult.textContent = e.message;
      sdResult.className = 'hint bad';
    }
  });
  sd.appendChild(sdTest);
  sd.appendChild(sdResult);
  sd.appendChild(el('div', 'hint',
    'Tip: drop your own images into the photos/<mood> folders next to the app — they are used as her photo pack. '
    + 'Put 1–3 clear face shots of her in photos/reference/ and (with ComfyUI + IPAdapter FaceID installed) '
    + 'every generated selfie will keep the same face.'));
  panel.appendChild(sd);

  // ---- Vision ----
  panel.appendChild(el('h2', '', 'Seeing your photos'));
  const vis = el('div', 'card');
  const visEnabled = toggle(s.vision_enabled);
  vis.appendChild(switchRow('Let her see photos you send',
    'uses a local vision model via Ollama (e.g. `ollama pull llava`)', visEnabled));
  const visModel = textInput(s.vision_model, 'llava');
  vis.appendChild(field('Vision model', visModel));
  panel.appendChild(vis);

  // ---- Character ----
  panel.appendChild(el('h2', '', 'Character'));
  const ch = el('div', 'card');
  const cName = textInput(s.character.name);
  const cPers = textArea(s.character.personality);
  const cApp = textArea(s.character.appearance);
  const uName = textInput(s.user_name, 'your name');
  ch.appendChild(field('Her name', cName));
  ch.appendChild(field('Personality', cPers));
  ch.appendChild(field('Appearance (also used for generated photos)', cApp));
  ch.appendChild(field('Your name', uName));
  const realistic = toggle(s.realistic_typing);
  ch.appendChild(switchRow('Realistic typing', 'she types at a human pace', realistic));
  panel.appendChild(ch);

  // ---- Save ----
  const saveBtn = el('button', 'btn', 'Save settings');
  const saveNote = el('span', 'hint', '');
  saveBtn.addEventListener('click', async () => {
    const updated = {
      ...s,
      ollama_url: ollamaUrl.value.trim(),
      model: modelSelect.value,
      sd_enabled: sdEnabled.checked,
      sd_backend: sdBackend.value,
      sd_url: sdUrl.value.trim(),
      sd_checkpoint: sdCheckpoint.value.trim(),
      sd_prompt_prefix: sdPrefix.value.trim(),
      vision_enabled: visEnabled.checked,
      vision_model: visModel.value.trim(),
      user_name: uName.value.trim(),
      realistic_typing: realistic.checked,
      character: {
        name: cName.value.trim() || 'Mira',
        personality: cPers.value.trim(),
        appearance: cApp.value.trim(),
      },
    };
    store.settings = await api.saveSettings(updated);
    saveNote.textContent = 'saved ✓';
    saveNote.className = 'ok';
    setTimeout(() => { saveNote.textContent = ''; }, 2000);
  });
  const saveRow = el('div', 'btn-row');
  saveRow.append(saveBtn, saveNote);
  panel.appendChild(saveRow);

  // ---- Memory ----
  panel.appendChild(el('h2', '', 'Memory & relationship'));
  const mem = el('div', 'card');
  try {
    const { facts, relationship } = await api.facts();
    const stageRow = el('div', 'switch-row');
    stageRow.appendChild(el('div', 'lbl', 'Relationship stage'));
    stageRow.appendChild(el('span', 'stage-badge', relationship.stage));
    mem.appendChild(stageRow);
    mem.appendChild(el('div', 'hint',
      `score ${relationship.score} · first chat ${new Date(relationship.first_chat_at).toLocaleDateString()}`));
    if (!facts.length) {
      mem.appendChild(el('div', 'hint', 'Nothing remembered yet — talk to her and she’ll start keeping notes.'));
    }
    for (const f of facts) {
      const row = el('div', 'fact-row');
      row.appendChild(el('span', 'cat', f.category));
      row.appendChild(el('span', 'txt', f.content));
      const del = el('button', '', '✕');
      del.title = 'Forget this';
      del.addEventListener('click', async () => {
        await api.deleteFact(f.id);
        row.remove();
      });
      row.appendChild(del);
      mem.appendChild(row);
    }
  } catch {
    mem.appendChild(el('div', 'hint bad', 'Could not load memory.'));
  }
  panel.appendChild(mem);

  // ---- Data ----
  panel.appendChild(el('h2', '', 'Your data'));
  const dataCard = el('div', 'card');
  dataCard.appendChild(el('div', 'hint',
    'Everything is stored locally in the data/ folder — conversations never leave this machine.'));
  const dataRow = el('div', 'btn-row');
  const exportBtn = el('a', 'btn secondary', 'Export everything');
  exportBtn.href = '/api/data/export';
  exportBtn.download = 'companion-export.json';
  const wipeBtn = el('button', 'btn danger', 'Erase everything');
  wipeBtn.addEventListener('click', async () => {
    const answer = prompt('This permanently deletes all messages, memories and settings.\nType DELETE to confirm:');
    if (answer === 'DELETE') {
      await api.wipe();
      location.hash = '#onboarding';
      location.reload();
    }
  });
  dataRow.append(exportBtn, wipeBtn);
  dataCard.appendChild(dataRow);
  panel.appendChild(dataCard);

  root.appendChild(panel);
}
