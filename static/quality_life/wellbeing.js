/* Wellbeing pages (docs/specs/11-bem-estar.md): session player with timer and
   breathing guide, relaxation sounds and the practice record.

   - Video and audio start only after a click ("Começar", "Tocar", "Fundo
     visual"); videos have no src until then.
   - With prefers-reduced-motion: reduce the video stays on its poster, the
     breathing circle does not scale and no GSAP loop runs; timers still work.
   - The only endless GSAP animation (breathing circle) is tagged data: 'loop'.
   - A practice is recorded once: when it completes, or when it stops after 60 s
     or more (button, closing the player or leaving the page). */
(() => {
    'use strict';
    const root = document.querySelector('[data-wellbeing]');
    if (!root) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    const MIN_RECORD_SECONDS = 60;
    const FADE_SECONDS = 4;
    const gsap = () => (!reduce.matches && window.gsap) || null;

    function record(kind, slug, seconds, completed) {
        const whole = Math.floor(seconds);
        if (whole < MIN_RECORD_SECONDS) return;
        const body = new FormData();
        body.append('csrfmiddlewaretoken', root.querySelector('input[name="csrfmiddlewaretoken"]').value);
        body.append('kind', kind);
        body.append('slug', slug);
        body.append('duration_seconds', String(whole));
        body.append('completed', completed ? '1' : '0');
        window.fetch(root.dataset.recordUrl, {
            method: 'POST', body, credentials: 'same-origin', keepalive: true,
        }).catch(() => {});
    }

    function clock(time) {
        const value = Math.max(0, Math.ceil(time));
        return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
    }

    // Counts only running time; robust to throttled timers (uses deltas).
    function stopwatch(onTick) {
        let running = false;
        let last = 0;
        let elapsed = 0;
        let interval = 0;
        const tick = () => {
            const now = performance.now();
            elapsed += (now - last) / 1000;
            last = now;
            onTick(elapsed);
        };
        return {
            start() {
                if (running) return;
                running = true;
                last = performance.now();
                interval = window.setInterval(tick, 250);
            },
            pause() {
                if (!running) return;
                tick();
                running = false;
                window.clearInterval(interval);
            },
            reset() {
                this.pause();
                elapsed = 0;
            },
            get elapsed() { return elapsed; },
            get running() { return running; },
        };
    }

    function startVideo(video, src) {
        if (reduce.matches) return; // poster stays still
        if (video.getAttribute('src') !== src) video.src = src;
        const promise = video.play();
        if (promise) promise.catch(() => {});
    }

    function stopVideo(video) {
        video.pause();
        video.removeAttribute('src');
        video.load();
    }

    // Gym: "Na cadeira" swaps the duration buttons --------------------------
    document.querySelectorAll('[data-chair-toggle]').forEach(toggle => {
        const card = toggle.closest('[data-gym-category]');
        toggle.addEventListener('change', () => {
            card.querySelectorAll('[data-chair]').forEach(button => { button.hidden = !toggle.checked; });
            card.querySelectorAll('[data-standing]').forEach(button => { button.hidden = toggle.checked; });
        });
    });

    // Session player ----------------------------------------------------------
    const dialog = document.querySelector('[data-player]');
    if (dialog && typeof dialog.showModal === 'function') {
        const sessions = Object.fromEntries(
            JSON.parse(document.getElementById('wb-sessions').textContent).map(item => [item.slug, item]),
        );
        const $ = selector => dialog.querySelector(selector);
        const video = $('[data-player-video]');
        const image = $('[data-player-image]');
        const imageToggle = $('[data-player-toggle-image]');
        const toggle = $('[data-player-toggle]');
        const previous = $('[data-player-previous]');
        const next = $('[data-player-next]');
        const stepTime = $('[data-player-step-time]');
        const totalTime = $('[data-player-total-time]');
        const progress = $('progress');
        const done = $('[data-player-done]');
        const circle = $('[data-breath-circle]');
        const breathLabel = $('[data-breath-label]');
        const noiseSelect = $('[data-player-noise]');
        const noiseVolume = $('[data-player-volume]');
        let session = null;
        let index = 0;
        let stepStart = 0;
        let started = false;
        let finished = false;
        let recorded = false;
        let showImage = false;
        let breathing = null;
        let lastSecond = -1;
        let opener = null;

        const watch = stopwatch(update);
        const step = () => session.steps[index];
        const offset = () => session.steps.slice(0, index).reduce((sum, item) => sum + item.seconds, 0);
        const volume = () => (noiseVolume ? Number(noiseVolume.value) / 100 : 0.4) * 0.8;

        function renderMedia() {
            const current = step();
            const hasVideo = Boolean(current.video);
            const material = !hasVideo || showImage;
            imageToggle.hidden = !(hasVideo && current.image);
            imageToggle.textContent = showImage ? 'Ver vídeo' : 'Ver imagem do material';
            image.hidden = !material;
            video.hidden = material;
            if (material) {
                image.src = current.image || current.poster;
                image.alt = `${current.title}: imagem do material Quality Life`;
                image.classList.toggle('is-material', Boolean(current.image));
                video.pause();
                return;
            }
            video.poster = current.poster;
            video.setAttribute('aria-label', `${current.title}: vídeo ilustrativo gerado por IA`);
            if (!started || reduce.matches) {
                if (video.hasAttribute('src')) stopVideo(video);
            } else if (watch.running) {
                startVideo(video, current.video);
            } else if (video.getAttribute('src') !== current.video) {
                video.src = current.video;
            }
        }

        function renderStep(direction = 0) {
            const current = step();
            const many = session.steps.length > 1;
            $('[data-player-position]').textContent = many ? `Exercício ${index + 1} de ${session.steps.length}` : session.label;
            $('[data-player-category]').textContent = many ? session.title : current.category;
            $('[data-player-title]').textContent = current.title;
            $('[data-player-text]').textContent = current.text;
            previous.hidden = !many;
            next.hidden = !many;
            previous.disabled = index === 0 || finished;
            next.disabled = index === session.steps.length - 1 || finished;
            showImage = false;
            renderMedia();
            update(watch.elapsed);
            const motion = gsap();
            if (motion && direction) {
                motion.fromTo([$('.wb-player__media'), $('.wb-player__info')], { opacity: 0, x: direction * 20 }, {
                    opacity: 1, x: 0, duration: 0.35, ease: 'power2.out', overwrite: true, clearProps: 'opacity,transform',
                });
            }
        }

        function update(elapsed) {
            if (!session || finished) return;
            let remaining = step().seconds - (elapsed - stepStart);
            if (remaining <= 0 && watch.running) {
                // Carry the overflow: a throttled background tab may skip steps.
                while (remaining <= 0) {
                    if (index === session.steps.length - 1) {
                        complete();
                        return;
                    }
                    stepStart += step().seconds;
                    index += 1;
                    remaining = step().seconds - (elapsed - stepStart);
                }
                renderStep(1);
                return;
            }
            const second = Math.ceil(remaining);
            stepTime.textContent = clock(remaining);
            totalTime.textContent = clock(session.duration - offset() - (elapsed - stepStart));
            progress.value = Math.min(1000, Math.round(((offset() + elapsed - stepStart) / session.duration) * 1000));
            const motion = gsap();
            if (motion && watch.running && second !== lastSecond && second <= 3) {
                motion.fromTo(stepTime, { scale: 1.15 }, { scale: 1, duration: 0.3, ease: 'power2.out', clearProps: 'transform' });
            }
            lastSecond = second;
            if (breathLabel && started && !finished) {
                const cycle = session.breathing.inhale + session.breathing.exhale;
                breathLabel.textContent = (elapsed % cycle) < session.breathing.inhale ? 'Inspire' : 'Expire';
            }
        }

        function startBreathing() {
            const motion = gsap();
            if (!circle || !motion) return;
            if (!breathing) {
                const { inhale, exhale } = session.breathing;
                breathing = motion.timeline({ repeat: -1, data: 'loop' })
                    .fromTo(circle, { scale: 0.62 }, { scale: 1, duration: inhale, ease: 'sine.inOut' })
                    .to(circle, { scale: 0.62, duration: exhale, ease: 'sine.inOut' });
            } else {
                breathing.resume();
            }
        }

        function startNoise() {
            if (!noiseSelect || !window.QLNoise) return;
            if (noiseSelect.value) window.QLNoise.play(noiseSelect.value, volume());
            else window.QLNoise.stop();
        }

        function play() {
            if (finished) return;
            const first = !started;
            started = true;
            watch.start();
            toggle.textContent = 'Pausar';
            renderMedia();
            startBreathing();
            if (first) startNoise();
            else if (window.QLNoise) window.QLNoise.resume();
        }

        function pause() {
            watch.pause();
            toggle.textContent = 'Continuar';
            video.pause();
            if (breathing) breathing.pause();
            if (window.QLNoise) window.QLNoise.pause();
        }

        function silence() {
            stopVideo(video);
            if (breathing) { breathing.kill(); breathing = null; }
            if (circle && window.gsap) window.gsap.set(circle, { clearProps: 'transform' });
            if (window.QLNoise) window.QLNoise.stop();
        }

        function complete() {
            finished = true; // before pause(): its last tick must not re-enter
            watch.pause();
            if (!recorded) { recorded = true; record(session.kind, session.slug, watch.elapsed, true); }
            progress.value = 1000;
            stepTime.textContent = clock(0);
            totalTime.textContent = clock(0);
            if (breathLabel) breathLabel.textContent = 'Concluída';
            if (window.QLNoise && window.QLNoise.playing) window.QLNoise.fadeOut(FADE_SECONDS);
            video.pause();
            if (breathing) { breathing.kill(); breathing = null; }
            toggle.textContent = 'Concluída';
            toggle.disabled = true;
            previous.disabled = true;
            next.disabled = true;
            done.hidden = false;
        }

        function stopSession() {
            if (!session) return;
            watch.pause();
            if (started && !recorded) { recorded = true; record(session.kind, session.slug, watch.elapsed, false); }
            silence();
        }

        function open(slug, button) {
            session = sessions[slug];
            if (!session) return;
            opener = button;
            index = 0;
            stepStart = 0;
            started = false;
            finished = false;
            recorded = false;
            lastSecond = -1;
            watch.reset();
            toggle.textContent = 'Começar';
            toggle.disabled = false;
            done.hidden = true;
            progress.value = 0;
            if (breathLabel) breathLabel.textContent = `Inspire ${session.breathing.inhale} s, expire ${session.breathing.exhale} s`;
            dialog.showModal();
            document.body.classList.add('wb-modal-open');
            renderStep();
            $('[data-player-title]').focus({ preventScroll: true });
        }

        document.querySelectorAll('[data-open-session]').forEach(button => {
            button.addEventListener('click', () => open(button.dataset.openSession, button));
        });
        toggle.addEventListener('click', () => (watch.running ? pause() : play()));
        previous.addEventListener('click', () => {
            if (index === 0) return;
            index -= 1;
            stepStart = watch.elapsed;
            renderStep(-1);
        });
        next.addEventListener('click', () => {
            if (index >= session.steps.length - 1) return;
            index += 1;
            stepStart = watch.elapsed;
            renderStep(1);
        });
        imageToggle.addEventListener('click', () => {
            showImage = !showImage;
            renderMedia();
        });
        if (noiseSelect) {
            noiseSelect.addEventListener('change', () => { if (watch.running) startNoise(); });
            noiseVolume.addEventListener('input', () => { if (window.QLNoise) window.QLNoise.setVolume(volume()); });
        }
        $('[data-player-close]').addEventListener('click', () => dialog.close());
        dialog.addEventListener('close', () => {
            stopSession();
            session = null;
            document.body.classList.remove('wb-modal-open');
            if (opener) opener.focus();
        });
        window.addEventListener('pagehide', stopSession);
        reduce.addEventListener('change', () => { if (reduce.matches && session) { video.pause(); if (breathing) { breathing.kill(); breathing = null; } } });
    }

    // Relaxamento ---------------------------------------------------------------
    const relax = document.querySelector('[data-relax]');
    if (relax) {
        const status = relax.querySelector('[data-relax-status]');
        const volumeInput = relax.querySelector('[data-relax-volume]');
        const stopButton = relax.querySelector('[data-relax-stop]');
        const backdrop = relax.querySelector('[data-backdrop]');
        const backdropVideo = relax.querySelector('[data-backdrop-video]');
        const backdropToggle = relax.querySelector('[data-backdrop-toggle]');
        const buttons = [...relax.querySelectorAll('[data-sound-play]')];
        const volume = () => (Number(volumeInput.value) / 100) * 0.8;
        const limit = () => Number(relax.querySelector('input[name="wb-timer"]:checked').value) * 60;
        let current = null;
        let fading = false;

        const watch = stopwatch(elapsed => {
            if (!current) return;
            const remaining = limit() - elapsed;
            if (remaining <= FADE_SECONDS && !fading) {
                fading = true;
                window.QLNoise.fadeOut(Math.max(0.5, remaining));
            }
            if (remaining <= 0) {
                finish(true);
                status.textContent = 'Tempo concluído. O som foi desligado.';
                return;
            }
            status.textContent = `Tocando: ${current.title} · ${clock(remaining)} restantes`;
        });

        function finish(completed) {
            if (!current) return;
            const ending = current;
            current = null; // before pause(): its last tick must not re-enter
            watch.pause();
            record('relaxamento', ending.slug, completed ? limit() : watch.elapsed, completed);
            if (!completed) window.QLNoise.stop();
            ending.button.setAttribute('aria-pressed', 'false');
            fading = false;
            watch.reset();
            stopButton.disabled = true;
            status.textContent = 'Nenhum som tocando.';
        }

        buttons.forEach(button => button.addEventListener('click', () => {
            const same = current && current.button === button;
            finish(false);
            if (same) return;
            const title = button.closest('[data-sound-card]').querySelector('h2').textContent;
            current = { slug: button.dataset.slug, title, button };
            window.QLNoise.play(button.dataset.noise, volume());
            button.setAttribute('aria-pressed', 'true');
            stopButton.disabled = false;
            watch.start();
            status.textContent = `Tocando: ${title} · ${clock(limit())} restantes`;
        }));
        stopButton.addEventListener('click', () => finish(false));
        volumeInput.addEventListener('input', () => window.QLNoise.setVolume(volume()));
        backdropToggle.addEventListener('change', () => {
            backdrop.hidden = !backdropToggle.checked;
            if (backdropToggle.checked) startVideo(backdropVideo, backdropVideo.dataset.src);
            else stopVideo(backdropVideo);
        });
        window.addEventListener('pagehide', () => finish(false));
    }
})();
