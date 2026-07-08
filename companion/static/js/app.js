// Boot + hash router.

import { api } from './api.js';
import { store } from './store.js';
import { renderChat } from './chat.js';
import { renderSettings } from './settings.js';
import { renderOnboarding } from './onboarding.js';

const root = document.getElementById('app');

async function route() {
  const hash = location.hash || '#chat';
  if (hash === '#settings') return renderSettings(root);
  if (hash === '#onboarding') return renderOnboarding(root);
  return renderChat(root);
}

async function boot() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
  document.getElementById('lightbox').addEventListener('click', (e) => {
    e.currentTarget.classList.add('hidden');
  });

  try {
    store.health = await api.health();
    store.settings = await api.settings();
  } catch {
    root.innerHTML = '<div class="panel"><div class="card">Could not reach the app server. '
      + 'Start it with <code>python run.py</code> and reload.</div></div>';
    return;
  }

  if (!store.health.onboarding_complete) {
    location.hash = '#onboarding';
  } else if (location.hash === '#onboarding') {
    location.hash = '#chat';
  }
  window.addEventListener('hashchange', route);
  route();
}

boot();
