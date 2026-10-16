/* Installable app (docs/specs/13-pwa-lembretes.md): registers the service
   worker and keeps the browser's install offer for the "Instalar o app" page. */
(() => {
  'use strict';
  const script = document.querySelector('script[data-sw]');
  const pwa = window.qlPwa = window.qlPwa || { installPrompt: null };
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    pwa.installPrompt = event;
    document.dispatchEvent(new CustomEvent('ql:installprompt'));
  });
  window.addEventListener('appinstalled', () => {
    pwa.installPrompt = null;
    document.dispatchEvent(new CustomEvent('ql:appinstalled'));
  });
  if (!script || !('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register(script.dataset.sw, { scope: '/' }).catch(() => {});
})();
