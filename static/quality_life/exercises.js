/* Exercise library and sequence dialog. The last exercise turns "Próximo" into
   "Concluir sequência"; time with the dialog open is recorded as a gym practice
   (practice.js, slug sequencia-exercicios) from 60 s on (spec 15). */
(() => {
    const dialog = document.querySelector('.exercise-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const cards = [...document.querySelectorAll('.exercise-card')];
    if (!cards.length) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const practice = window.QLPractice;
    const next = dialog.querySelector('[data-next]');
    const previous = dialog.querySelector('[data-previous]');
    const done = dialog.querySelector('[data-sequence-done]');
    let current = 0;
    let opener;
    let openedAt = 0;
    let concluded = false;
    const openSeconds = () => (performance.now() - openedAt) / 1000;
    document.querySelectorAll('.exercise-enhanced').forEach(element => { element.hidden = false; });
    document.querySelectorAll('.exercise-instructions').forEach(element => { element.hidden = true; });
    function show(index, direction = 0) {
        current = index;
        const card = cards[index];
        dialog.querySelector('[data-sequence-position]').textContent = `Exercício ${index + 1} de ${cards.length}`;
        dialog.querySelector('progress').value = index + 1;
        dialog.querySelector('[data-detail-category]').textContent = card.dataset.category;
        dialog.querySelector('#exercise-title').textContent = card.querySelector('h3').textContent;
        const sourceImage = card.querySelector('img');
        const detailImage = dialog.querySelector('[data-detail-image]');
        detailImage.src = sourceImage.src;
        detailImage.alt = sourceImage.alt;
        const instruction = dialog.querySelector('[data-detail-instruction]');
        instruction.replaceChildren(...[...card.querySelector('.exercise-instructions').children].filter(element => element.tagName !== 'SUMMARY').map(element => element.cloneNode(true)));
        const last = index === cards.length - 1;
        previous.disabled = index === 0 || concluded;
        next.textContent = last ? 'Concluir sequência' : 'Próximo →';
        next.disabled = concluded;
        dialog.scrollTop = 0;
        dialog.querySelector('.exercise-detail').scrollTop = 0;
        dialog.querySelector('#exercise-title').focus({ preventScroll: true });
        // Smooth swap: the new exercise slides in from the side it comes from.
        if (window.gsap && !motion.matches) window.gsap.fromTo('.exercise-detail', { opacity: 0, x: direction * 24, y: direction ? 0 : 12 }, { opacity: 1, x: 0, y: 0, duration: .35, ease: 'power2.out', overwrite: true, clearProps: 'opacity,transform' });
    }
    function conclude() {
        concluded = true;
        previous.disabled = true;
        next.disabled = true;
        const seconds = openSeconds();
        const title = document.createElement('strong');
        title.textContent = 'Sequência concluída';
        const detail = document.createElement('span');
        const link = document.createElement('a');
        link.href = document.querySelector('[data-progress-url]').dataset.progressUrl;
        link.textContent = 'Ver meu progresso →';
        if (seconds < practice.MIN_RECORD_SECONDS) {
            detail.textContent = `${practice.SHORT} `;
        } else {
            detail.textContent = `Você praticou ${practice.minutes(seconds)} min. `;
            practice.record('ginastica', 'sequencia-exercicios', seconds, true).then(stored => {
                detail.textContent = stored === null
                    ? 'Não foi possível registrar a prática. Tente de novo mais tarde. '
                    : `Prática registrada: ${stored} min. `;
            });
        }
        done.replaceChildren(title, detail, link);
        title.tabIndex = -1;
        title.focus({ preventScroll: true });
    }
    function open(index, button) {
        opener = button;
        openedAt = performance.now();
        concluded = false;
        done.replaceChildren();
        dialog.showModal();
        document.body.classList.add('exercise-modal-open');
        show(index);
    }
    document.querySelectorAll('[data-open-exercise]').forEach(button => button.addEventListener('click', () => open(Number(button.dataset.openExercise), button)));
    document.querySelector('[data-start-sequence]').addEventListener('click', event => open(0, event.currentTarget));
    dialog.querySelector('[data-close-exercise]').addEventListener('click', () => dialog.close());
    previous.addEventListener('click', () => { if (current > 0 && !concluded) show(current - 1, -1); });
    next.addEventListener('click', () => {
        if (concluded) return;
        if (current < cards.length - 1) show(current + 1, 1);
        else conclude();
    });
    dialog.addEventListener('click', event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener('close', () => {
        document.body.classList.remove('exercise-modal-open');
        if (!concluded) {
            concluded = true;
            practice.recordAndNotify('ginastica', 'sequencia-exercicios', openSeconds(), false);
        }
        opener?.focus();
    });
    window.addEventListener('pagehide', () => {
        if (!dialog.open || concluded) return;
        concluded = true;
        practice.record('ginastica', 'sequencia-exercicios', openSeconds(), false);
    });
    document.querySelectorAll('[data-category]:is(button)').forEach(button => button.addEventListener('click', () => {
        document.querySelectorAll('[data-category]:is(button)').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        cards.forEach(card => { card.hidden = button.dataset.category !== 'all' && card.dataset.category !== button.dataset.category; });
    }));
})();
