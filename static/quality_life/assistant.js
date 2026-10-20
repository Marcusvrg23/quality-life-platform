/* Assistente Quality (docs/specs/18-assistente.md). The conversation lives
   only in this tab's memory (no storage): reloading or leaving clears it.
   Answers are shown as plain text (textContent), never as HTML. On opening,
   the assistant greets with the suggestion of this period of the day. */
(() => {
  'use strict';
  const form = document.getElementById('assistant-form');
  if (!form) return;
  const log = document.getElementById('assistant-log');
  const input = document.getElementById('assistant-input');
  const clear = document.getElementById('assistant-clear');
  const submit = form.querySelector('button[type="submit"]');
  const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]').value;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MAX_TURNS = 12;
  let history = [];

  // "• " items written inline become one per line.
  const tidy = text => text.replace(/\s+•\s+/g, '\n• ').trim();

  function bubble(role) {
    const item = document.createElement('li');
    item.className = `wb-assistant__msg wb-assistant__msg--${role}`;
    const who = document.createElement('span');
    who.className = 'wb-assistant__who';
    who.textContent = role === 'user' ? 'Você' : 'Assistente';
    const body = document.createElement('p');
    item.append(who, body);
    log.append(item);
    return { item, body };
  }

  function add(role, text) {
    const { item, body } = bubble(role);
    body.textContent = text;
    item.scrollIntoView({ block: 'nearest' });
  }

  // Animated "digitando…" bubble while waiting for the answer.
  function typing() {
    const { item, body } = bubble('assistant');
    item.classList.add('wb-assistant__msg--typing');
    body.setAttribute('aria-label', 'Escrevendo');
    body.innerHTML = '<span class="wb-dot"></span><span class="wb-dot"></span><span class="wb-dot"></span>';
    item.scrollIntoView({ block: 'nearest' });
    return { item, body };
  }

  // Reveal the answer a few characters at a time (instant with reduced motion).
  function reveal(target, text) {
    const { item, body } = target;
    item.classList.remove('wb-assistant__msg--typing');
    body.removeAttribute('aria-label');
    if (reduce) {
      body.textContent = text;
      return Promise.resolve();
    }
    body.textContent = '';
    return new Promise(resolve => {
      let shown = 0;
      const step = () => {
        shown = Math.min(text.length, shown + 3);
        body.textContent = text.slice(0, shown);
        if (shown < text.length) setTimeout(step, 16);
        else resolve();
      };
      step();
    });
  }

  function busy(on) {
    submit.disabled = on;
    input.disabled = on;
  }

  async function greet() {
    const pending = typing();
    let text = null;
    try {
      const response = await fetch(form.dataset.suggestion, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data && typeof data.suggestion === 'string') text = tidy(data.suggestion);
    } catch (error) {
      // No suggestion: the chat starts empty.
    }
    if (!text) {
      pending.item.remove();
      return;
    }
    await reveal(pending, text);
    history.push({ role: 'assistant', content: text });
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
    const pending = typing();
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
      if (data && typeof data.answer === 'string') answer = tidy(data.answer);
      ok = response.ok;
    } catch (error) {
      // Network error: the generic answer above.
    }
    await reveal(pending, answer);
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

  greet();
})();
