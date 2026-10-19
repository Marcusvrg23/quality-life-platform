/* Assistente Quality (docs/specs/18-assistente.md). The conversation lives
   only in this tab's memory (no storage): reloading or leaving clears it.
   Answers are shown as plain text (textContent), never as HTML. */
(() => {
  'use strict';
  const form = document.getElementById('assistant-form');
  if (!form) return;
  const log = document.getElementById('assistant-log');
  const input = document.getElementById('assistant-input');
  const typing = document.getElementById('assistant-typing');
  const clear = document.getElementById('assistant-clear');
  const submit = form.querySelector('button[type="submit"]');
  const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]').value;
  const MAX_TURNS = 12;
  let history = [];

  function add(role, text) {
    const item = document.createElement('li');
    item.className = `wb-assistant__msg wb-assistant__msg--${role}`;
    const who = document.createElement('span');
    who.className = 'wb-assistant__who';
    who.textContent = role === 'user' ? 'Você' : 'Assistente';
    const body = document.createElement('p');
    body.textContent = text;
    item.append(who, body);
    log.append(item);
    item.scrollIntoView({ block: 'nearest' });
  }

  function busy(on) {
    typing.hidden = !on;
    submit.disabled = on;
    input.disabled = on;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    add('user', text);
    history.push({ role: 'user', content: text });
    history = history.slice(-MAX_TURNS);
    input.value = '';
    busy(true);
    let answer = 'O assistente não conseguiu responder agora. Tente de novo em instantes.';
    let ok = false;
    try {
      const response = await fetch(form.dataset.endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
        body: JSON.stringify({ messages: history }),
      });
      const data = await response.json().catch(() => null);
      if (data && typeof data.answer === 'string') answer = data.answer;
      ok = response.ok;
    } catch (error) {
      // Network error: the generic answer above.
    }
    add('assistant', answer);
    if (ok) history.push({ role: 'assistant', content: answer });
    else history.pop();  // the question can be sent again
    busy(false);
    input.focus();
  });

  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  clear.addEventListener('click', () => {
    history = [];
    log.replaceChildren();
    input.focus();
  });
})();
