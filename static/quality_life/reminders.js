/* Break reminders (docs/specs/13-pwa-lembretes.md). While any Quality Life
   page is open, schedules the next slot of the owner's agenda and shows a
   notification, or an in-page notice when notifications are unavailable.
   Notification permission is requested only by the "Ativar lembretes" click. */
(() => {
  'use strict';
  const script = document.querySelector('script[data-schedule]');
  if (!script) return;
  const MESSAGE = 'Hora da pausa. Que tal alguns minutos de Ginástica Laboral?';
  const SLOT_KEY = 'ql-reminder-slot';
  // A tab that slept past a slot by more than this skips it instead of nagging late.
  const LATE_MS = 5 * 60 * 1000;
  // Long timeouts drift (and overflow after ~24 days): wake up at least hourly.
  const MAX_WAIT_MS = 60 * 60 * 1000;
  const supported = 'Notification' in window && 'serviceWorker' in navigator;
  let schedule = null;
  let timer = null;

  const toMinutes = value => {
    const [hours, minutes] = value.split(':').map(Number);
    return hours * 60 + minutes;
  };

  // Slots are start + k * interval, strictly between start and end, on the
  // chosen ISO weekdays (1 = Monday), in the device's local time. An end at or
  // before the start is on the next day (night shift); the shift belongs to
  // the day it starts, so yesterday's shift may still be running.
  function nextSlot(after) {
    const start = toMinutes(schedule.start);
    let end = toMinutes(schedule.end);
    if (end <= start) end += 24 * 60;
    for (let offset = -1; offset < 8; offset += 1) {
      const day = new Date(after.getFullYear(), after.getMonth(), after.getDate() + offset);
      if (!schedule.days.includes(day.getDay() || 7)) continue;
      for (let at = start + schedule.interval; at < end; at += schedule.interval) {
        // Minutes past 24:00 roll over into the next day.
        const slot = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 0, at);
        if (slot > after) return slot;
      }
    }
    return null;
  }

  // One tab per slot when several are open (best effort).
  function claim(slot) {
    try {
      if (localStorage.getItem(SLOT_KEY) === String(slot.getTime())) return false;
      localStorage.setItem(SLOT_KEY, String(slot.getTime()));
    } catch (error) {
      // Storage blocked: this tab shows the reminder anyway.
    }
    return true;
  }

  async function notify() {
    if (!supported || Notification.permission !== 'granted') return false;
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (!registration) return false;
      await registration.showNotification(MESSAGE, {
        icon: script.dataset.icon,
        tag: 'ql-pausa',
        data: { url: script.dataset.target },
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  function showNotice() {
    let notice = document.querySelector('[data-reminder-notice]');
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'ql-reminder';
      notice.dataset.reminderNotice = '';
      notice.setAttribute('role', 'status');
      const text = document.createElement('p');
      text.textContent = MESSAGE;
      const actions = document.createElement('div');
      actions.className = 'ql-reminder__actions';
      const start = document.createElement('a');
      start.className = 'ql-reminder__start';
      start.href = script.dataset.target;
      start.textContent = 'Começar a pausa';
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'ql-reminder__close';
      close.textContent = 'Agora não';
      close.addEventListener('click', () => { notice.hidden = true; });
      actions.append(start, close);
      notice.append(text, actions);
      document.body.append(notice);
    }
    notice.hidden = false;
  }

  async function remind(slot) {
    if (!claim(slot)) return;
    if (!(await notify())) showNotice();
  }

  function plan() {
    clearTimeout(timer);
    if (!schedule || !schedule.active) return;
    const now = new Date();
    const slot = nextSlot(now);
    if (!slot) return;
    timer = setTimeout(() => {
      const late = Date.now() - slot.getTime();
      if (late >= 0 && late <= LATE_MS) remind(slot);
      plan();
    }, Math.min(slot - now, MAX_WAIT_MS));
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') plan();
  });

  fetch(script.dataset.schedule, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
    .then(response => (response.ok ? response.json() : null))
    .then(data => {
      schedule = data;
      plan();
    })
    .catch(() => {})
    .finally(() => { script.dataset.state = 'loaded'; });

  // Reminders page: permission is asked only here, on the click.
  const status = document.querySelector('[data-reminder-status]');
  if (status) {
    const active = status.dataset.active === '1';
    let text;
    if (!supported) text = 'Este navegador não mostra notificações: o aviso aparece dentro da página.';
    else if (Notification.permission === 'granted') text = 'Notificações permitidas neste aparelho.';
    else if (Notification.permission === 'denied') text = 'As notificações estão bloqueadas neste navegador: o aviso aparece dentro da página.';
    else if (active) text = 'Sem permissão de notificação: o aviso aparece dentro da página.';
    else text = 'Ao ativar, o navegador pergunta se pode mostrar notificações.';
    status.textContent = text;
  }
  const activate = document.querySelector('[data-reminder-activate]');
  if (activate) {
    activate.addEventListener('click', event => {
      if (activate.dataset.asked || !supported || Notification.permission !== 'default') return;
      event.preventDefault();
      activate.dataset.asked = '1';
      const submit = () => activate.click();
      try {
        Promise.resolve(Notification.requestPermission()).then(submit, submit);
      } catch (error) {
        submit();
      }
    });
  }
})();
