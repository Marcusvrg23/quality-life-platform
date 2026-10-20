/* Hoje: the assistant's suggestion of this period of the day (spec 18).
   The card stays hidden unless a suggestion arrives. Plain text only. */
(() => {
  'use strict';
  const card = document.querySelector('[data-assistant-suggestion]');
  if (!card) return;
  const text = card.querySelector('[data-assistant-suggestion-text]');
  fetch(card.dataset.url, { credentials: 'same-origin', headers: { Accept: 'application/json' }, cache: 'no-store' })
    .then(response => (response.ok ? response.json() : null))
    .then(data => {
      if (!data || typeof data.suggestion !== 'string' || !data.suggestion.trim()) return;
      text.textContent = data.suggestion.replace(/\s+•\s+/g, '\n• ').trim();
      card.hidden = false;
    })
    .catch(() => {});
})();
