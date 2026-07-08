// Input bar: autosizing textarea, photo attach with preview chip, send.

import { api } from './api.js';
import { store } from './store.js';

export function buildComposer(onSend) {
  const frag = document.createDocumentFragment();

  const chip = document.createElement('div');
  chip.className = 'attach-chip hidden';
  frag.appendChild(chip);

  const bar = document.createElement('div');
  bar.className = 'composer';

  const attachBtn = document.createElement('button');
  attachBtn.className = 'icon-btn';
  attachBtn.textContent = '📷';
  attachBtn.title = 'Send a photo';

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/*';
  fileInput.className = 'hidden';

  const ta = document.createElement('textarea');
  ta.rows = 1;
  ta.placeholder = 'Message…';

  const sendBtn = document.createElement('button');
  sendBtn.className = 'send-btn';
  sendBtn.textContent = '↑';
  sendBtn.title = 'Send';

  let uploadId = null;

  function autosize() {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }

  function clearChip() {
    uploadId = null;
    chip.classList.add('hidden');
    chip.textContent = '';
  }

  attachBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file) return;
    chip.classList.remove('hidden');
    chip.textContent = 'uploading…';
    try {
      const res = await api.uploadPhoto(file);
      uploadId = res.upload_id;
      chip.textContent = '';
      const img = document.createElement('img');
      img.src = '/' + res.path;
      const label = document.createElement('span');
      label.textContent = 'photo attached';
      const x = document.createElement('button');
      x.textContent = '✕';
      x.addEventListener('click', clearChip);
      chip.append(img, label, x);
    } catch {
      chip.textContent = 'upload failed';
      setTimeout(clearChip, 2000);
    }
  });

  function doSend() {
    const text = ta.value.trim();
    if ((!text && !uploadId) || store.sending) return;
    const upload = uploadId;
    ta.value = '';
    autosize();
    clearChip();
    onSend(text, upload);
  }

  sendBtn.addEventListener('click', doSend);
  ta.addEventListener('input', autosize);
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  });
  store.on('sending', (busy) => { sendBtn.disabled = busy; });

  bar.append(attachBtn, fileInput, ta, sendBtn);
  frag.appendChild(bar);
  return frag;
}
