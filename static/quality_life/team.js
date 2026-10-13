/* Copies a freshly generated invitation link; the link exists only on this page. */
(() => {
  'use strict';
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const input = document.getElementById(button.dataset.copy);
    if (!input) return;
    try {
      await navigator.clipboard.writeText(input.value);
    } catch {
      input.select();
      document.execCommand('copy');
    }
    button.textContent = 'Copiado';
    window.setTimeout(() => { button.textContent = 'Copiar'; }, 2500);
  });
})();
