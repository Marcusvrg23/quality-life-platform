/* "Instalar o app" (docs/specs/13-pwa-lembretes.md): the install button is
   shown only when the browser offered installation (beforeinstallprompt,
   kept by pwa.js); opened from the home screen, the page says so. */
(() => {
  'use strict';
  const button = document.querySelector('[data-install-button]');
  const installed = document.querySelector('[data-installed]');
  if (!button || !installed) return;
  const pwa = () => window.qlPwa || {};
  const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

  function showInstalled() {
    installed.hidden = false;
    button.hidden = true;
    document.querySelectorAll('[data-install-guide]').forEach(guide => { guide.hidden = true; });
  }

  function offer() {
    button.hidden = !pwa().installPrompt;
  }

  if (standalone) {
    showInstalled();
    return;
  }
  document.addEventListener('ql:installprompt', offer);
  document.addEventListener('ql:appinstalled', showInstalled);
  offer();
  button.addEventListener('click', async () => {
    const prompt = pwa().installPrompt;
    if (!prompt) return;
    pwa().installPrompt = null;
    button.hidden = true;
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice && choice.outcome === 'accepted') showInstalled();
    } catch (error) {
      // The browser withdrew the offer; the manual steps stay on screen.
    }
  });
})();
