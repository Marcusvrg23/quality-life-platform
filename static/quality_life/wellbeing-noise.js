/* White, pink and brown noise generated with the Web Audio API (no audio
   files). The AudioContext is created lazily on the first play(), which the
   pages call only from a click, so nothing sounds before the person asks. */
window.QLNoise = (() => {
    'use strict';
    const SECONDS = 4;
    const buffers = {};
    let context = null;
    let source = null;
    let gain = null;
    let fadeTimer = 0;

    function audio() {
        if (!context) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            context = new AudioContext();
        }
        return context;
    }

    function buffer(type) {
        if (buffers[type]) return buffers[type];
        const ctx = audio();
        const length = ctx.sampleRate * SECONDS;
        const result = ctx.createBuffer(1, length, ctx.sampleRate);
        const data = result.getChannelData(0);
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
        buffers[type] = result;
        return result;
    }

    function stop() {
        window.clearTimeout(fadeTimer);
        if (source) {
            try { source.stop(); } catch (error) { /* already stopped */ }
            source.disconnect();
        }
        if (gain) gain.disconnect();
        source = null;
        gain = null;
    }

    function play(type, volume) {
        stop();
        const ctx = audio();
        if (ctx.state === 'suspended') ctx.resume().catch(() => {});
        gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.8);
        gain.connect(ctx.destination);
        source = ctx.createBufferSource();
        source.buffer = buffer(type);
        source.loop = true;
        source.connect(gain);
        source.start();
    }

    function setVolume(volume) {
        if (!gain) return;
        const now = context.currentTime;
        gain.gain.cancelScheduledValues(now);
        gain.gain.setTargetAtTime(volume, now, 0.1);
    }

    function fadeOut(seconds) {
        if (!gain) return;
        const now = context.currentTime;
        const current = gain.gain.value;
        gain.gain.cancelScheduledValues(now);
        gain.gain.setValueAtTime(current, now);
        gain.gain.linearRampToValueAtTime(0, now + seconds);
        const playing = source;
        window.clearTimeout(fadeTimer);
        fadeTimer = window.setTimeout(() => { if (source === playing) stop(); }, seconds * 1000);
    }

    return {
        play,
        stop,
        setVolume,
        fadeOut,
        pause() { if (context && context.state === 'running') context.suspend().catch(() => {}); },
        resume() { if (context && context.state === 'suspended') context.resume().catch(() => {}); },
        get playing() { return Boolean(source); },
    };
})();
