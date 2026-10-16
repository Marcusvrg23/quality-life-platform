/* Practice record and the "what counted" notice (docs/specs/15-app-empresas.md),
   shared by Ginástica, Meditação, Relaxamento, Exercícios and Aulas.

   - The page holds {% csrf_token %} and data-record-url on [data-record-root].
   - A practice under 60 s is never sent; the server applies the same rule.
   - The notice lives in the page ([data-practice-notice], role="status") and
     clears itself; it is meant for exits back to the page, not inside a modal. */
window.QLPractice = (() => {
    'use strict';
    const MIN_RECORD_SECONDS = 60;
    const NOTICE_MS = 6000;
    const SHORT = 'Práticas com menos de 1 minuto não entram no seu progresso.';
    const FAILED = 'Não foi possível registrar a prática. Tente de novo mais tarde.';
    let timer = 0;

    const minutes = seconds => Math.floor(seconds / 60);

    // Resolves to the minutes stored by the server, or null (short or failed).
    function record(kind, slug, seconds, completed) {
        const whole = Math.floor(seconds);
        const root = document.querySelector('[data-record-root]');
        if (whole < MIN_RECORD_SECONDS || !root) return Promise.resolve(null);
        const body = new FormData();
        body.append('csrfmiddlewaretoken', root.querySelector('input[name="csrfmiddlewaretoken"]').value);
        body.append('kind', kind);
        body.append('slug', slug);
        body.append('duration_seconds', String(whole));
        body.append('completed', completed ? '1' : '0');
        return window.fetch(root.dataset.recordUrl, {
            method: 'POST', body, credentials: 'same-origin', keepalive: true,
        }).then(response => (response.ok ? response.json() : null))
            .then(data => (data ? data.minutes : null))
            .catch(() => null);
    }

    function notify(text) {
        const notice = document.querySelector('[data-practice-notice]');
        if (!notice) return;
        window.clearTimeout(timer);
        notice.textContent = text;
        notice.classList.add('is-visible');
        timer = window.setTimeout(() => {
            notice.classList.remove('is-visible');
            notice.textContent = '';
        }, NOTICE_MS);
    }

    // Records and tells the person what entered their progress.
    function recordAndNotify(kind, slug, seconds, completed) {
        if (Math.floor(seconds) < MIN_RECORD_SECONDS) {
            notify(SHORT);
            return Promise.resolve(null);
        }
        return record(kind, slug, seconds, completed).then(stored => {
            notify(stored === null ? FAILED : `Prática registrada: ${stored} min.`);
            return stored;
        });
    }

    return { MIN_RECORD_SECONDS, SHORT, minutes, record, notify, recordAndNotify };
})();
