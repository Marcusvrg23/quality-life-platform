/* Relaxation sounds generated with the Web Audio API (no audio files):
   - white, pink and brown noise;
   - forest, ocean, rain and music, ported (audio only, same numbers) from the
     approved preview docs/design/sons/sons-relaxamento.html.
   The single AudioContext is created lazily on the first play(), which the
   pages call only from a click, so nothing sounds before the person asks.
   stop() and fadeOut() also clear the sound's timers and stop its sources. */
window.QLNoise = (() => {
    'use strict';
    const SECONDS = 4;
    const FADE = 2; // fade-in of each generated sound, in seconds
    // Loudness balance between sounds (measured RMS in the approved preview).
    const LEVEL = { rain: 1.6, ocean: 0.55, forest: 4.2, music: 1.3 };
    const buffers = {};
    let ctx = null;
    let comp = null;
    let impulse = null;
    let stereo = null;
    let current = null; // { gain, sources, timers }
    let fadeTimer = 0;

    const rand = (a, b) => a + Math.random() * (b - a);
    const pick = list => list[Math.floor(Math.random() * list.length)];

    function audio() {
        if (!ctx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            ctx = new AudioContext();
        }
        return ctx;
    }

    function makeNoise(type, seconds, channels) {
        const length = Math.floor(audio().sampleRate * seconds);
        const result = ctx.createBuffer(channels, length, ctx.sampleRate);
        for (let channel = 0; channel < channels; channel += 1) {
            const data = result.getChannelData(channel);
            let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, last = 0;
            for (let i = 0; i < length; i += 1) {
                const white = Math.random() * 2 - 1;
                if (type === 'pink') {
                    // Paul Kellet's refined pink noise filter.
                    b0 = 0.99886 * b0 + white * 0.0555179;
                    b1 = 0.99332 * b1 + white * 0.0750759;
                    b2 = 0.969 * b2 + white * 0.153852;
                    b3 = 0.8665 * b3 + white * 0.3104856;
                    b4 = 0.55 * b4 + white * 0.5329522;
                    b5 = -0.7616 * b5 - white * 0.016898;
                    data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
                    b6 = white * 0.115926;
                } else if (type === 'brown') {
                    last = (last + 0.02 * white) / 1.02;
                    data[i] = last * 3.5;
                } else {
                    data[i] = white * 0.5;
                }
            }
        }
        return result;
    }

    function buffer(type) {
        if (!buffers[type]) buffers[type] = makeNoise(type, SECONDS, 1);
        return buffers[type];
    }

    // Generated sounds: audio of the approved preview, same numbers ------------

    function makeImpulse(seconds, decay) {
        const len = Math.floor(ctx.sampleRate * seconds);
        const buf = ctx.createBuffer(2, len, ctx.sampleRate);
        for (let ch = 0; ch < 2; ch++) {
            const d = buf.getChannelData(ch);
            for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
        }
        return buf;
    }
    function ensure() {
        if (comp) return;
        comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 3;
        comp.connect(ctx.destination);
        stereo = { white: makeNoise('white', 6, 2), pink: makeNoise('pink', 8, 2), brown: makeNoise('brown', 8, 2) };
        impulse = makeImpulse(2.6, 2.4);
    }
    function loopNoise(type, dest) {
        const src = ctx.createBufferSource(); src.buffer = stereo[type]; src.loop = true;
        src.connect(dest); src.start(ctx.currentTime, rand(0, stereo[type].duration)); return src;
    }
    function scheduler(tick) { // lookahead scheduler on the audio clock
        let next = ctx.currentTime;
        const id = setInterval(() => { while (next < ctx.currentTime + 0.25) next = tick(next); }, 50);
        return () => clearInterval(id);
    }
    function voice(level, dest) { // per-sound output with fade
        const out = ctx.createGain(); out.gain.setValueAtTime(0.0001, ctx.currentTime);
        out.gain.exponentialRampToValueAtTime(level, ctx.currentTime + FADE); out.connect(dest);
        // Per-sound reverb that feeds the same faded output, so stopping silences its tail too.
        out.rv = ctx.createConvolver(); out.rv.buffer = impulse;
        const rg = ctx.createGain(); rg.gain.value = 0.5; out.rv.connect(rg).connect(out);
        return out;
    }

    // ---------- Chuva ----------
    function rain(out) {
        const parts = { sources: [], timers: [] };
        const bedF = ctx.createBiquadFilter(); bedF.type = 'bandpass'; bedF.frequency.value = 2200; bedF.Q.value = 0.45;
        const bedG = ctx.createGain(); bedG.gain.value = 0.32; bedF.connect(bedG).connect(out);
        parts.sources.push(loopNoise('pink', bedF));
        const rumF = ctx.createBiquadFilter(); rumF.type = 'lowpass'; rumF.frequency.value = 180;
        const rumG = ctx.createGain(); rumG.gain.value = 0.18; rumF.connect(rumG).connect(out);
        parts.sources.push(loopNoise('brown', rumF));
        let density = 35;
        parts.timers.push(scheduler(t => {
            if (Math.random() < 0.02) { density = rand(20, 60); bedG.gain.setTargetAtTime(rand(0.24, 0.4), t, 2); }
            const dur = rand(0.005, 0.03);
            const s = ctx.createBufferSource(); s.buffer = stereo.white;
            const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = rand(2000, 8000); f.Q.value = rand(2, 6);
            const g = ctx.createGain(); const peak = rand(0.05, 0.28);
            g.gain.setValueAtTime(peak, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.04);
            const p = ctx.createStereoPanner(); p.pan.value = rand(-1, 1);
            s.connect(f).connect(g).connect(p).connect(out);
            s.start(t, rand(0, 5)); s.stop(t + dur + 0.06);
            if (Math.random() < 0.12) { // bigger drop: short rising "plink"
                const o = ctx.createOscillator(); o.type = 'sine';
                const f0 = rand(900, 1700); o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f0 * rand(1.6, 2.4), t + 0.02);
                const og = ctx.createGain(); og.gain.setValueAtTime(rand(0.02, 0.05), t); og.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
                const op = ctx.createStereoPanner(); op.pan.value = rand(-0.9, 0.9);
                o.connect(og).connect(op).connect(out); o.start(t); o.stop(t + 0.06);
            }
            return t + (-Math.log(1 - Math.random()) / density); // random (Poisson) spacing
        }));
        return parts;
    }

    // ---------- Mar ----------
    function ocean(out) {
        const parts = { sources: [], timers: [] };
        const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 300; lp.Q.value = 0.4;
        const g = ctx.createGain(); g.gain.value = 0.12;
        const pan = ctx.createStereoPanner(); pan.pan.value = 0;
        lp.connect(g).connect(pan).connect(out);
        parts.sources.push(loopNoise('brown', lp));
        const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 3200;
        const fg = ctx.createGain(); fg.gain.value = 0.0001;
        hp.connect(fg).connect(pan);
        parts.sources.push(loopNoise('white', hp));
        let side = 1;
        parts.timers.push(scheduler(t => {
            const D = rand(6, 12), rise = D * 0.58, crest = t + rise, brk = crest + D * 0.14, end = t + D;
            const top = rand(1100, 2100);
            lp.frequency.setTargetAtTime(top, t, rise / 3);
            g.gain.setTargetAtTime(rand(0.5, 0.75), t, rise / 3);
            fg.gain.setTargetAtTime(0.0001, t, 0.5);
            fg.gain.setTargetAtTime(rand(0.08, 0.16), crest - 0.4, 0.25);
            fg.gain.setTargetAtTime(0.0001, brk, 0.6);
            lp.frequency.setTargetAtTime(rand(260, 420), brk, (end - brk) / 3);
            g.gain.setTargetAtTime(rand(0.1, 0.18), brk, (end - brk) / 3);
            side = -side; pan.pan.setTargetAtTime(side * rand(0.15, 0.35), t, D / 3);
            return end;
        }));
        return parts;
    }

    // ---------- Floresta (vento baixo, folhas, riacho, sabiá, piados e rolinha) ----------
    // Rajada de vento 0..1, função do tempo: controla o vento e a densidade das folhas.
    function gustAt(t) {
        const g = 0.42 + 0.28 * Math.sin(2 * Math.PI * t / 23) + 0.18 * Math.sin(2 * Math.PI * t / 9.7 + 1.3) + 0.08 * Math.sin(2 * Math.PI * t / 4.1 + 0.4);
        return Math.min(1, Math.max(0, g));
    }
    // Uma nota de pássaro: seno com deslize de altura, ataque macio e um pouco do 2º harmônico
    function birdNote(t, f0, f1, d, amp, dest, vib = 0) {
        [[1, 1], [2, 0.08]].forEach(([h, a]) => {
            const o = ctx.createOscillator(); o.type = 'sine';
            o.frequency.setValueAtTime(f0 * h, t); o.frequency.exponentialRampToValueAtTime(f1 * h, t + d);
            if (vib) { const v = ctx.createOscillator(); v.frequency.value = rand(22, 32); const vg = ctx.createGain(); vg.gain.value = f0 * h * vib; v.connect(vg).connect(o.frequency); v.start(t); v.stop(t + d + 0.05); }
            const e = ctx.createGain(); e.gain.setValueAtTime(0.0001, t);
            e.gain.exponentialRampToValueAtTime(amp * a, t + Math.min(0.02, d * 0.3));
            e.gain.setValueAtTime(amp * a, t + d * 0.6);
            e.gain.exponentialRampToValueAtTime(0.0001, t + d);
            o.connect(e).connect(dest); o.start(t); o.stop(t + d + 0.05);
        });
    }
    // Cadeia de cada ave: posição no estéreo, distância (agudos e volume caem, reverb sobe)
    function birdChain(out, pan, far, level) {
        const p = ctx.createStereoPanner(); p.pan.value = pan;
        const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 9000 - 4500 * far;
        const dry = ctx.createGain(); dry.gain.value = level * (1 - 0.7 * far);
        const wet = ctx.createGain(); wet.gain.value = level * (0.5 + 0.8 * far);
        p.connect(lp); lp.connect(dry).connect(out); lp.connect(wet).connect(out.rv);
        setTimeout(() => { p.disconnect(); lp.disconnect(); dry.disconnect(); wet.disconnect(); }, 9000);
        return p;
    }
    // Pássaro cantor (tipo sabiá): frase melódica de 4 a 7 notas, cada frase diferente
    function songbird(t, out, pan, far, shift = 1) {
        const dest = birdChain(out, pan, far, 0.05);
        const scale = [1900, 2130, 2390, 2530, 2840, 3190, 3380].map(f => f * shift);
        let at = t, i = Math.floor(rand(1, 5));
        const n = Math.round(rand(4, 7));
        for (let k = 0; k < n; k++) {
            i = Math.min(scale.length - 1, Math.max(0, i + pick([-2, -1, 1, 1, 2])));
            const f = scale[i] * rand(0.99, 1.01), kind = Math.random(), d = rand(0.09, 0.24);
            if (kind < 0.35) birdNote(at, f * 0.9, f * 1.08, d, 1, dest);             // sobe
            else if (kind < 0.65) birdNote(at, f * 1.08, f * 0.92, d, 1, dest);       // desce
            else if (kind < 0.85) birdNote(at, f, f, d * 1.2, 0.9, dest, 0.02);       // nota com vibrato
            else { birdNote(at, f * 1.2, f * 1.1, 0.04, 0.7, dest); birdNote(at + 0.06, f * 1.2, f * 1.1, 0.04, 0.7, dest); } // "ti-ti"
            at += d + rand(0.04, 0.12);
        }
        return at;
    }
    // Piados ao longe (passarinhos conversando baixinho no fundo)
    function chirps(t, out) {
        const dest = birdChain(out, rand(-0.9, 0.9), rand(0.6, 0.9), 0.045);
        let at = t; const f = rand(3600, 4800), n = Math.round(rand(2, 5));
        for (let k = 0; k < n; k++) { birdNote(at, f * 1.12, f * 0.86, rand(0.035, 0.06), 1, dest); at += rand(0.08, 0.15); }
    }
    // Rolinha: arrulho grave e lento "hu-HUU-hu-hu"
    function dove(t, out) {
        const dest = birdChain(out, rand(-0.75, -0.4), 0.55, 0.08);
        const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1300; lp.connect(dest);
        const base = rand(440, 520);
        [[0, 0.22, 1, 1.04], [0.34, 0.5, 1.08, 0.95], [1.0, 0.26, 0.97, 0.94], [1.42, 0.26, 0.96, 0.92]].forEach(([dt, d, a, b]) => birdNote(t + dt, base * a, base * b, d, 0.9, lp));
    }
    function forest(out) {
        const parts = { sources: [], timers: [] };
        // Vento: grave e baixo, só sobe um pouco nas rajadas
        const wf = ctx.createBiquadFilter(); wf.type = 'lowpass'; wf.frequency.value = 480; wf.Q.value = 0.3;
        const wg = ctx.createGain(); wg.gain.value = 0.03; wf.connect(wg).connect(out);
        parts.sources.push(loopNoise('brown', wf));
        parts.timers.push(scheduler(t => {
            const g = gustAt(t);
            wg.gain.setTargetAtTime(0.02 + 0.045 * g, t, 0.4);
            wf.frequency.setTargetAtTime(360 + 380 * g, t, 0.6);
            return t + 0.25;
        }));
        // Folhas: grãos curtos e agudos, mais densos quando venta
        parts.timers.push(scheduler(t => {
            const g = gustAt(t), dur = rand(0.02, 0.09);
            const s = ctx.createBufferSource(); s.buffer = stereo.white;
            const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 2400;
            const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = rand(3500, 7500); bp.Q.value = 0.8;
            const e = ctx.createGain(); const peak = rand(0.012, 0.04) * (0.4 + g);
            e.gain.setValueAtTime(0.0001, t); e.gain.exponentialRampToValueAtTime(peak, t + 0.006); e.gain.exponentialRampToValueAtTime(0.0001, t + dur);
            const pp = ctx.createStereoPanner(); pp.pan.value = rand(-1, 1);
            s.connect(hp).connect(bp).connect(e).connect(pp).connect(out);
            s.start(t, rand(0, 5)); s.stop(t + dur + 0.02);
            const density = 3 + 45 * g * g;
            return t + (-Math.log(1 - Math.random()) / density);
        }));
        // Riacho: três faixas com variação rápida + bolhas, à esquerda
        const brook = ctx.createStereoPanner(); brook.pan.value = -0.45;
        const bm = ctx.createGain(); bm.gain.value = 1; bm.connect(brook).connect(out);
        [[520, 2.2], [1150, 2.6], [2300, 3.2]].forEach(([fq, q]) => {
            const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = fq; f.Q.value = q;
            const g = ctx.createGain(); g.gain.value = 0.03; f.connect(g).connect(bm);
            parts.sources.push(loopNoise('white', f));
            parts.timers.push(scheduler(t => { g.gain.setTargetAtTime(rand(0.012, 0.05), t, 0.025); return t + rand(0.03, 0.08); }));
        });
        parts.timers.push(scheduler(t => {
            const o = ctx.createOscillator(); o.type = 'sine';
            const f0 = rand(380, 950), d = rand(0.025, 0.05);
            o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f0 * rand(1.3, 1.9), t + d);
            const e = ctx.createGain(); e.gain.setValueAtTime(0.0001, t); e.gain.exponentialRampToValueAtTime(rand(0.012, 0.035), t + 0.006); e.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.02);
            o.connect(e).connect(bm); o.start(t); o.stop(t + d + 0.03);
            return t + (-Math.log(1 - Math.random()) / 7);
        }));
        // Aves: piados ao longe, um sabiá que às vezes recebe resposta do outro lado, e a rolinha de vez em quando
        parts.timers.push(scheduler(t => { if (t > ctx.currentTime + 0.01) chirps(t, out); return t + rand(2.5, 7); }));
        parts.timers.push(scheduler(t => {
            if (t > ctx.currentTime + 0.01) {
                const side = Math.random() < 0.5 ? -1 : 1;
                const end = songbird(t, out, side * rand(0.45, 0.8), 0.2);
                if (Math.random() < 0.55) { const t2 = end + rand(0.8, 2.2); songbird(t2, out, -side * rand(0.5, 0.9), 0.65, rand(0.92, 1.08)); }
            }
            return t + rand(7, 15);
        }));
        parts.timers.push(scheduler(t => { if (t > ctx.currentTime + 0.5) dove(t, out); return t + rand(16, 30); }));
        return parts;
    }

    // ---------- Acordes suaves ----------
    const midi = m => 440 * Math.pow(2, (m - 69) / 12);
    const CHORDS = [[48, 52, 55, 59], [45, 48, 52, 55], [41, 45, 48, 52], [43, 47, 50, 52]]; // Cmaj7 Am7 Fmaj7 G6
    const BELLS = [[72, 74, 76, 79, 81], [69, 72, 74, 76, 79], [65, 69, 72, 74, 77], [67, 71, 74, 76, 79]];
    function music(out) {
        const parts = { sources: [], timers: [] };
        const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1300; lp.Q.value = 0.3;
        const bus = ctx.createGain(); bus.gain.value = 0.9; lp.connect(bus); bus.connect(out); bus.connect(out.rv);
        const delay = ctx.createDelay(1); delay.delayTime.value = 0.45; const fb = ctx.createGain(); fb.gain.value = 0.32;
        const dl = ctx.createBiquadFilter(); dl.type = 'lowpass'; dl.frequency.value = 2000; const dg = ctx.createGain(); dg.gain.value = 0.35;
        bus.connect(delay); delay.connect(dl).connect(fb).connect(delay); dl.connect(dg).connect(out);
        let i = 0; const LEN = 16;
        parts.timers.push(scheduler(t => {
            const chord = CHORDS[i % CHORDS.length];
            chord.forEach(m => {
                [['sine', -4], ['triangle', 4]].forEach(([type, cents]) => {
                    const o = ctx.createOscillator(); o.type = type; o.frequency.value = midi(m); o.detune.value = cents + rand(-2, 2);
                    const e = ctx.createGain(); e.gain.setValueAtTime(0.0001, t);
                    e.gain.exponentialRampToValueAtTime(type === 'sine' ? 0.05 : 0.025, t + 5);
                    e.gain.setValueAtTime(type === 'sine' ? 0.05 : 0.025, t + LEN - 1);
                    e.gain.exponentialRampToValueAtTime(0.0001, t + LEN + 6);
                    o.connect(e).connect(lp); o.start(t); o.stop(t + LEN + 6.2);
                });
            });
            const bells = BELLS[i % BELLS.length];
            for (let at = t + rand(3, 6); at < t + LEN; at += rand(4, 8)) {
                const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = midi(pick(bells));
                const e = ctx.createGain(); e.gain.setValueAtTime(0.0001, at);
                e.gain.exponentialRampToValueAtTime(0.035, at + 0.02); e.gain.exponentialRampToValueAtTime(0.0001, at + 3.5);
                const p = ctx.createStereoPanner(); p.pan.value = rand(-0.6, 0.6);
                o.connect(e).connect(p).connect(bus); o.start(at); o.stop(at + 3.6);
            }
            i++; return t + LEN;
        }));
        // 200 Hz / 210 Hz layer, always on.
        [[200, -1], [210, 1]].forEach(([f, side]) => {
            const o = ctx.createOscillator(); o.frequency.value = f;
            const g = ctx.createGain(); g.gain.value = 0.035; const p = ctx.createStereoPanner(); p.pan.value = side;
            o.connect(g).connect(p).connect(out); o.start(); parts.sources.push(o);
        });
        return parts;
    }

    const MAKERS = { rain, ocean, forest, music };

    // Public API ---------------------------------------------------------------

    function stop() {
        window.clearTimeout(fadeTimer);
        if (!current) return;
        current.timers.forEach(clear => clear());
        current.sources.forEach(source => {
            try { source.stop(); } catch (error) { /* already stopped */ }
            source.disconnect();
        });
        // Also silences one-shot nodes the scheduler already queued.
        current.gain.disconnect();
        current = null;
    }

    function play(type, volume) {
        stop();
        audio();
        if (ctx.state === 'suspended') ctx.resume().catch(() => {});
        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.8);
        if (MAKERS[type]) {
            ensure();
            gain.connect(comp);
            current = { gain, ...MAKERS[type](voice(LEVEL[type], gain)) };
            return;
        }
        gain.connect(ctx.destination);
        const source = ctx.createBufferSource();
        source.buffer = buffer(type);
        source.loop = true;
        source.connect(gain);
        source.start();
        current = { gain, sources: [source], timers: [] };
    }

    function setVolume(volume) {
        if (!current) return;
        const now = ctx.currentTime;
        current.gain.gain.cancelScheduledValues(now);
        current.gain.gain.setTargetAtTime(volume, now, 0.1);
    }

    function fadeOut(seconds) {
        if (!current) return;
        const { gain } = current;
        const now = ctx.currentTime;
        const value = gain.gain.value;
        gain.gain.cancelScheduledValues(now);
        gain.gain.setValueAtTime(value, now);
        gain.gain.linearRampToValueAtTime(0, now + seconds);
        const fading = current;
        window.clearTimeout(fadeTimer);
        fadeTimer = window.setTimeout(() => { if (current === fading) stop(); }, seconds * 1000);
    }

    return {
        play,
        stop,
        setVolume,
        fadeOut,
        pause() { if (ctx && ctx.state === 'running') ctx.suspend().catch(() => {}); },
        resume() { if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {}); },
        get playing() { return Boolean(current); },
    };
})();
