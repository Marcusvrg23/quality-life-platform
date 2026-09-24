(() => {
    const dialog = document.querySelector('.exercise-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const cards = [...document.querySelectorAll('.exercise-card')];
    if (!cards.length) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let current = 0;
    let opener;
    document.querySelectorAll('.exercise-enhanced').forEach(element => { element.hidden = false; });
    document.querySelectorAll('.exercise-instructions').forEach(element => { element.hidden = true; });
    function show(index) {
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
        dialog.querySelector('[data-previous]').disabled = index === 0;
        dialog.querySelector('[data-next]').disabled = index === cards.length - 1;
        dialog.scrollTop = 0;
        dialog.querySelector('.exercise-detail').scrollTop = 0;
        dialog.querySelector('#exercise-title').focus({ preventScroll: true });
        if (window.gsap && !motion.matches) window.gsap.fromTo('.exercise-detail', { opacity: .4, y: 8 }, { opacity: 1, y: 0, duration: .3, overwrite: true, clearProps: 'all' });
    }
    function open(index, button) {
        opener = button;
        dialog.showModal();
        document.body.classList.add('exercise-modal-open');
        show(index);
    }
    document.querySelectorAll('[data-open-exercise]').forEach(button => button.addEventListener('click', () => open(Number(button.dataset.openExercise), button)));
    document.querySelector('[data-start-sequence]').addEventListener('click', event => open(0, event.currentTarget));
    dialog.querySelector('[data-close-exercise]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-previous]').addEventListener('click', () => { if (current > 0) show(current - 1); });
    dialog.querySelector('[data-next]').addEventListener('click', () => { if (current < cards.length - 1) show(current + 1); });
    dialog.addEventListener('click', event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener('close', () => { document.body.classList.remove('exercise-modal-open'); opener?.focus(); });
    document.querySelectorAll('[data-category]:is(button)').forEach(button => button.addEventListener('click', () => {
        document.querySelectorAll('[data-category]:is(button)').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        cards.forEach(card => { card.hidden = button.dataset.category !== 'all' && card.dataset.category !== button.dataset.category; });
    }));
    if (window.gsap && !motion.matches) {
        window.gsap.fromTo('.exercise-card, .exercise-guide', { opacity: .5, y: 12 }, { opacity: 1, y: 0, duration: .45, stagger: .04, clearProps: 'all' });
    }
})();
