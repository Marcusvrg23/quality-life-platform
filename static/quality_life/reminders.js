/* Break reminders and per-account notifications (docs/specs/13-pwa-lembretes.md).
   While any Quality Life page is open, schedules the next slot of the owner's
   agenda and shows a notification, or an in-page notice when this device does
   not receive the server's push for this account.
   A device receives an account's push only after "Ativar notificações neste
   aparelho" (or "Ativar lembretes") on that account. "Desativar
   notificações neste aparelho" removes only this account's row on the
   server: the browser subscription is never cancelled, so other accounts on
   the same device keep receiving theirs. Signing out and deactivating the
   break reminders keep the device (tips keep arriving). Notification
   permission is requested only by a click. */
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
  // Signing out or deactivating never waits longer than this for the push service.
  const CANCEL_TIMEOUT_MS = 2500;
  const supported = 'Notification' in window && 'serviceWorker' in navigator;
  const pushSupported = supported && 'PushManager' in window;
  const isIphone = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  let schedule = null;
  let timer = null;
  // 'active' when this device receives the server's push; otherwise why not.
  let pushState = 'pending';

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
    // The server already sent this reminder to this device.
    if (pushState === 'active') return;
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

  // Web Push -----------------------------------------------------------------

  function csrfToken() {
    const input = document.querySelector('input[name=csrfmiddlewaretoken]');
    if (input) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function post(url, payload) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      keepalive: true,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    });
  }

  function toKeyBytes(base64url) {
    const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, char => char.charCodeAt(0));
  }

  function toBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    bytes.forEach(byte => { binary += String.fromCharCode(byte); });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function sameKey(subscription, key) {
    const current = subscription.options && subscription.options.applicationServerKey;
    if (!current) return true;
    try {
      return toBase64url(current) === key.replace(/=+$/, '');
    } catch (error) {
      return true;
    }
  }

  function withTimeout(promise, ms) {
    return Promise.race([promise, new Promise(resolve => setTimeout(resolve, ms))]);
  }

  async function registration() {
    if (!pushSupported) return null;
    // No worker registered (or still registering): never block on "ready".
    const existing = await navigator.serviceWorker.getRegistration().catch(() => null);
    if (!existing) return null;
    const ready = navigator.serviceWorker.ready.catch(() => null);
    return (await withTimeout(ready, 5000)) || null;
  }

  async function currentSubscription() {
    const reg = await registration();
    return reg ? { reg, subscription: await reg.pushManager.getSubscription() } : null;
  }

  // Why this device cannot receive push at all, or null when it can.
  function blocker() {
    if (!schedule) return 'unavailable';
    if (!supported) return 'unsupported';
    if (Notification.permission === 'denied') return 'denied';
    if (!schedule.push_key) return 'server';
    if (!pushSupported) return 'nopush';
    return null;
  }

  async function registered(subscription) {
    try {
      const response = await post(script.dataset.status, { endpoint: subscription.endpoint });
      if (!response.ok) return false;
      return (await response.json()).registered === true;
    } catch (error) {
      return false;
    }
  }

  // Load: only reads the state, never subscribes on its own.
  async function syncPush() {
    const blocked = blocker();
    if (blocked) return blocked;
    if (Notification.permission !== 'granted') return 'default';
    try {
      const current = await currentSubscription();
      if (!current) return 'failed';
      const { subscription } = current;
      if (!subscription || !sameKey(subscription, schedule.push_key)) return 'off';
      return (await registered(subscription)) ? 'active' : 'off';
    } catch (error) {
      return 'failed';
    }
  }

  async function enablePush() {
    const blocked = blocker();
    if (blocked) return blocked;
    if (Notification.permission === 'denied') return 'denied';
    if (Notification.permission !== 'granted') return 'default';
    try {
      const current = await currentSubscription();
      if (!current) return 'failed';
      let { subscription } = current;
      if (subscription && !sameKey(subscription, schedule.push_key)) {
        // The server key changed: the old subscription can no longer receive.
        await subscription.unsubscribe().catch(() => false);
        subscription = null;
      }
      if (!subscription) {
        subscription = await current.reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: toKeyBytes(schedule.push_key),
        });
      }
      const response = await post(script.dataset.subscribe, subscription.toJSON());
      return response.ok ? 'active' : 'failed';
    } catch (error) {
      return 'failed';
    }
  }

  // Removes only this account's row: never subscription.unsubscribe(), which
  // would silence every account on this device.
  async function disablePush() {
    try {
      const current = await currentSubscription();
      const subscription = current && current.subscription;
      if (subscription) {
        const response = await withTimeout(post(script.dataset.unsubscribe, { endpoint: subscription.endpoint }), CANCEL_TIMEOUT_MS * 2);
        if (response && !response.ok && response.status !== 404) return 'active';
      }
    } catch (error) {
      return 'failed';
    }
    return 'off';
  }

  // Reminders page: status text and the two buttons ---------------------------

  const status = document.querySelector('[data-push-status]');
  const enableButton = document.querySelector('[data-push-enable]');
  const disableButton = document.querySelector('[data-push-disable]');
  const ENABLE_AFTER_RELOAD = 'ql-push-enable';

  function describe(state) {
    switch (state) {
      case 'active':
        return 'Notificações ativas neste aparelho para esta conta, mesmo com o app fechado. As outras contas deste aparelho têm a própria escolha.';
      case 'off':
        return 'Este aparelho não recebe as notificações desta conta. Toque em Ativar notificações neste aparelho.';
      case 'default':
        return 'Este aparelho não recebe as notificações desta conta. Ao tocar em Ativar notificações neste aparelho, o navegador pergunta se pode mostrar notificações.';
      case 'unsupported':
        return isIphone && !standalone
          ? 'No iPhone, adicione o app à tela de início (iOS 16.4 ou mais novo) para receber notificações. Até lá, o aviso aparece dentro da página.'
          : 'Este navegador não mostra notificações: o aviso aparece dentro da página.';
      case 'denied':
        return 'As notificações deste site estão bloqueadas nas configurações do navegador ou do celular. Libere-as lá e volte a esta página.';
      case 'server':
        return 'Este servidor ainda não envia notificações com o app fechado: o aviso aparece com o app aberto.';
      case 'nopush':
        return 'Este navegador não recebe notificações com o app fechado: o aviso aparece com o app aberto.';
      case 'failed':
        return 'Não foi possível ativar as notificações neste aparelho. Tente de novo em instantes.';
      case 'working':
        return 'Um instante…';
      default:
        return 'Verificando as notificações deste aparelho…';
    }
  }

  function showStatus(state) {
    pushState = state;
    if (status) {
      status.textContent = describe(state);
      status.dataset.push = state;
    }
    if (enableButton) {
      enableButton.hidden = !['off', 'default', 'failed'].includes(state);
      enableButton.disabled = false;
    }
    if (disableButton) {
      disableButton.hidden = state !== 'active';
      disableButton.disabled = false;
    }
  }

  function run(action) {
    if (enableButton) enableButton.disabled = true;
    if (disableButton) disableButton.disabled = true;
    return action().then(showStatus, () => showStatus('failed'));
  }

  if (status) {
    // Provisional text before the agenda arrives.
    if (!supported) showStatus('unsupported');
    else if (Notification.permission === 'denied') showStatus('denied');
    else showStatus('pending');
  }

  function takeEnableFlag() {
    try {
      const flag = sessionStorage.getItem(ENABLE_AFTER_RELOAD) === '1';
      sessionStorage.removeItem(ENABLE_AFTER_RELOAD);
      return flag;
    } catch (error) {
      return false;
    }
  }

  const loaded = fetch(script.dataset.schedule, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
    .then(response => (response.ok ? response.json() : null))
    .then(data => {
      schedule = data;
      plan();
      // "Ativar lembretes" asked for the permission before the reload.
      if (takeEnableFlag() && supported && Notification.permission === 'granted') return enablePush();
      return syncPush();
    })
    .then(state => showStatus(state || 'failed'))
    .catch(() => showStatus('failed'))
    .finally(() => { script.dataset.state = 'loaded'; });

  if (enableButton) {
    enableButton.addEventListener('click', () => {
      // The permission prompt must start inside the click, before any await.
      let asking = Promise.resolve();
      if (supported && Notification.permission === 'default') {
        try {
          asking = Promise.resolve(Notification.requestPermission()).catch(() => null);
        } catch (error) {
          // Nothing to ask: enablePush reports the state.
        }
      }
      run(() => Promise.all([asking, loaded]).then(enablePush));
    });
  }
  if (disableButton) {
    disableButton.addEventListener('click', () => {
      loaded.then(() => run(disablePush));
    });
  }

  // "Ativar lembretes" also turns on this device for this account.
  const activate = document.querySelector('[data-reminder-activate]');
  if (activate) {
    activate.addEventListener('click', event => {
      if (activate.dataset.asked || !supported || Notification.permission === 'denied') return;
      try {
        sessionStorage.setItem(ENABLE_AFTER_RELOAD, '1');
      } catch (error) {
        // Storage blocked: the person uses the device button instead.
      }
      if (Notification.permission !== 'default') return;
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
