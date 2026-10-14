/* Light motion for the app and auth pages (docs/specs/09-app-dark.md).
   Cards in the first screen rise in once (y 24 -> 0, stagger 0.08) and
   interactive glass cards follow a fine pointer with a soft glow (CSS reads
   --mx/--my). With prefers-reduced-motion: reduce or without GSAP nothing
   runs, and nothing is hidden before GSAP takes over. */
(() => {
    'use strict';
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)');
    const CARDS = [
        '.dashboard-intro', '.dashboard-notice', '.dashboard-recommendation', '.dashboard-hero', '.dashboard-link',
        '.exercise-heading', '.exercise-safety', '.exercise-card', '.lessons-intro', '.lesson-card',
        '.team > *', '.exec-report > *', '.ql-main--assessment > .card', '.legal-settings',
        '.login-form-wrap', '.foundation',
    ].join(', ');
    const GLOW = '.dashboard-link, .dashboard-recommendation, .exercise-card, .lesson-card';

    function enter() {
        if (reduce.matches || !window.gsap) return;
        const items = [...document.querySelectorAll(CARDS)].filter(element => {
            const box = element.getBoundingClientRect();
            return box.width > 0 && box.top < window.innerHeight && box.bottom > 0;
        });
        if (!items.length) return;
        window.gsap.fromTo(items, { opacity: 0, y: 24 }, {
            opacity: 1, y: 0, duration: 0.6, ease: 'power2.out', stagger: 0.08, clearProps: 'opacity,transform',
        });
    }

    let frame = 0;
    let pending = null;
    function glow(event) {
        if (reduce.matches || !fine.matches) return;
        pending = event;
        if (frame) return;
        frame = window.requestAnimationFrame(() => {
            frame = 0;
            const card = pending.target instanceof Element ? pending.target.closest(GLOW) : null;
            if (!card) return;
            const box = card.getBoundingClientRect();
            card.style.setProperty('--mx', `${Math.round(pending.clientX - box.left)}px`);
            card.style.setProperty('--my', `${Math.round(pending.clientY - box.top)}px`);
        });
    }

    document.addEventListener('pointermove', glow, { passive: true });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enter);
    else enter();
})();
