/* Lessons (spec 15): "ended" shows "Aula concluída" on the card. Watched time is
   summed from playback progress (seeks do not count) and reset at each end;
   the lesson is recorded as a gym practice (practice.js, slug aula-<slug>) only
   when one viewing reaches 60 s, so the current 10 s videos never record. */
(() => {
    'use strict';
    const practice = window.QLPractice;
    if (!practice) return;
    document.querySelectorAll('[data-lesson]').forEach(card => {
        const video = card.querySelector('video');
        const done = card.querySelector('[data-lesson-done]');
        let watched = 0;
        let last = null;
        video.addEventListener('playing', () => { last = video.currentTime; });
        video.addEventListener('timeupdate', () => {
            if (last !== null && !video.paused && !video.seeking) {
                const step = video.currentTime - last;
                // Normal playback advances in small steps; a jump is a seek.
                if (step > 0 && step < 1.5) watched += step;
            }
            last = video.currentTime;
        });
        video.addEventListener('seeking', () => { last = null; });
        video.addEventListener('ended', () => {
            done.textContent = 'Aula concluída';
            const seconds = watched;
            watched = 0;
            last = null;
            practice.recordAndNotify('ginastica', card.dataset.lesson, seconds, true);
        });
    });
})();
