/* Canvas light for the landing page: aurora, light ribbons and particles.
   One requestAnimationFrame loop drives the fixed page background
   (#ql-ambient) and the layered scenes registered by home.js. Nothing runs
   with prefers-reduced-motion: reduce, while the tab is hidden, or for a
   scene that is off screen. If the average frame over 30 frames exceeds
   24 ms the density drops, the cursor trail stops and <html> gets .ql-lite.
   Exposes window.QLAmbient. */
(function () {
    "use strict";

    var TAU = Math.PI * 2;
    var COLORS = ["25,180,165", "126,91,163", "211,38,142"];
    var FRAME_BUDGET_MS = 24;
    var SEGMENTS = 36;
    var DODGE_RADIUS = 150;
    var REPEL_RADIUS = 120;
    var REPEL_MAX = 18;
    var REPEL_LERP = 0.05;
    // Stroke passes per ribbon: [width factor, alpha factor, white core,
    // repeated for every strand]. Wide passes are the glow around the band.
    var PASSES = [
        [9, 0.1, false, false],
        [3.4, 0.22, false, false],
        [1, 0.9, false, true],
        [0.35, 0.55, true, true],
    ];
    var STRAND_GAP = 5;
    // Ribbon specs, as fractions of the canvas:
    // [y0, y1, bow, amp, width, alpha, strands].
    var SCENES = {
        hero: {
            back: {
                ribbons: [
                    [0.98, 0.3, -0.16, 0.045, 2.2, 0.9, 3],
                    [0.78, 0.62, 0.14, 0.035, 1.6, 0.7, 2],
                    [1.06, 0.12, -0.04, 0.03, 1.2, 0.5, 1],
                ],
                particles: [44, 22],
                depth: 10,
                bokeh: true,
            },
            front: {
                ribbons: [[1.02, 0.74, -0.1, 0.03, 1.4, 0.8, 2]],
                particles: [10, 5],
                depth: 24,
            },
        },
        "hero-mobile": {
            back: {
                ribbons: [
                    [0.86, 0.5, -0.12, 0.03, 2, 0.9, 3],
                    [0.7, 0.78, 0.1, 0.025, 1.4, 0.65, 2],
                ],
                particles: [44, 22],
                depth: 8,
                bokeh: true,
            },
            front: {
                ribbons: [[0.96, 0.64, -0.06, 0.02, 1.3, 0.8, 2]],
                particles: [10, 5],
                depth: 16,
            },
        },
        cta: {
            back: {
                ribbons: [
                    [0.34, 0.2, -0.1, 0.04, 2.2, 0.9, 3],
                    [0.18, 0.42, 0.08, 0.03, 1.4, 0.65, 2],
                ],
                particles: [34, 16],
                depth: 10,
                bokeh: true,
            },
            front: {
                ribbons: [[0.72, 0.5, -0.06, 0.02, 1.3, 0.75, 2]],
                particles: [8, 4],
                depth: 22,
            },
        },
    };

    var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    var fineQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
    var fields = [];
    var byName = {};
    var enabled = !reduceQuery.matches;
    var lite = false;
    var frameId = 0;
    var lastTime = 0;
    var warmup = 0;
    var samples = [];
    var scrollY = window.scrollY;
    var rectsDirty = true;
    var sprites = null;
    var trail = [];
    var pointer = { x: -1e4, y: -1e4, sx: -1e4, sy: -1e4, on: false, nx: 0, ny: 0 };

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    function isSmall() {
        return window.innerWidth < 600;
    }

    // Soft glowing dots, pre-rendered once per colour and drawn as images.
    function makeSprites() {
        return COLORS.map(function (rgb) {
            var canvas = document.createElement("canvas");
            canvas.width = canvas.height = 64;
            var ctx = canvas.getContext("2d");
            var glow = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
            glow.addColorStop(0, "rgba(255,255,255,1)");
            glow.addColorStop(0.16, "rgba(" + rgb + ",0.95)");
            glow.addColorStop(0.45, "rgba(" + rgb + ",0.28)");
            glow.addColorStop(1, "rgba(" + rgb + ",0)");
            ctx.fillStyle = glow;
            ctx.fillRect(0, 0, 64, 64);
            return canvas;
        });
    }

    function makeRibbon(spec, index) {
        return {
            spec: spec,
            freq: rand(0.7, 1.4),
            speed: rand(0.22, 0.42) * (index % 2 ? -1 : 1),
            phase: rand(0, TAU),
            shift: index % COLORS.length,
            scroll: 0,
            gradient: null,
            offsets: new Float32Array(SEGMENTS),
        };
    }

    function makeParticle(w, h, big) {
        return {
            x: rand(0, w),
            y: rand(0, h),
            r: big ? rand(7, 18) : rand(1.2, 4.2),
            a: big ? rand(0.08, 0.22) : rand(0.35, 0.9),
            c: Math.floor(rand(0, COLORS.length)),
            vx: rand(-6, 6),
            vy: rand(-22, -6),
            tw: rand(0.6, 1.8),
            ph: rand(0, TAU),
            depth: rand(0.04, 0.22),
            ox: 0,
            oy: 0,
        };
    }

    function Layer(canvas, config, maxDpr) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.config = config;
        this.maxDpr = maxDpr;
        this.w = 0;
        this.h = 0;
        this.dpr = 0;
        this.px = -1e4;
        this.py = -1e4;
        this.ox = 0;
        this.oy = 0;
        this.rect = null;
        this.points = new Float32Array(SEGMENTS * 2);
        this.ribbons = [];
        this.particles = [];
    }

    Layer.prototype.resize = function (force) {
        var dpr = Math.min(window.devicePixelRatio || 1, this.maxDpr);
        var w = this.canvas.clientWidth;
        var h = this.canvas.clientHeight;
        if (!w || !h) {
            return;
        }
        // Mobile toolbars change the height while scrolling; ignore small jumps.
        if (!force && w === this.w && dpr === this.dpr && Math.abs(h - this.h) < 120) {
            return;
        }
        this.w = w;
        this.h = h;
        this.dpr = dpr;
        this.canvas.width = Math.round(w * dpr);
        this.canvas.height = Math.round(h * dpr);
        this.ribbons = this.config.ribbons.map(makeRibbon);
        var count = this.config.particles[isSmall() ? 1 : 0];
        if (lite) {
            count = Math.ceil(count / 2);
        }
        this.particles = [];
        for (var i = 0; i < count; i += 1) {
            this.particles.push(makeParticle(w, h, this.config.bokeh && i % 6 === 0));
        }
    };

    // Resolve a ribbon spec to pixels: scene ribbons use canvas fractions,
    // page ribbons (scroll = 1) are anchored to section edges in the document.
    Layer.prototype.ribbonBase = function (ribbon) {
        var s = ribbon.spec;
        if (ribbon.scroll) {
            return [s[0] - scrollY, s[1] - scrollY, s[2], s[3]];
        }
        return [s[0] * this.h, s[1] * this.h, s[2] * this.h, s[3] * this.h];
    };

    Layer.prototype.drawRibbon = function (ribbon, t) {
        var ctx = this.ctx;
        var w = this.w;
        var base = this.ribbonBase(ribbon);
        var top = Math.min(base[0], base[1]) - Math.abs(base[2]) - base[3] * 2;
        var bottom = Math.max(base[0], base[1]) + Math.abs(base[2]) + base[3] * 2;
        if (bottom < -60 || top > this.h + 60) {
            return;
        }
        var pts = this.points;
        for (var i = 0; i < SEGMENTS; i += 1) {
            var u = i / (SEGMENTS - 1);
            var x = (-0.08 + 1.16 * u) * w;
            var wave =
                0.7 * Math.sin(TAU * ribbon.freq * u + t * ribbon.speed + ribbon.phase) +
                0.3 * Math.sin(TAU * ribbon.freq * 1.7 * u - t * ribbon.speed * 0.6 + ribbon.phase * 2);
            var y = base[0] + (base[1] - base[0]) * u + base[2] * Math.sin(Math.PI * u) + base[3] * wave;
            // Ribbons bend away from the cursor or finger.
            var dx = x - this.px;
            var dy = y - this.py;
            var distance = Math.sqrt(dx * dx + dy * dy);
            var target = 0;
            if (distance < DODGE_RADIUS) {
                target = (dy >= 0 ? 1 : -1) * (1 - distance / DODGE_RADIUS) * 46;
            }
            ribbon.offsets[i] += (target - ribbon.offsets[i]) * 0.08;
            pts[i * 2] = x;
            pts[i * 2 + 1] = y + ribbon.offsets[i];
        }
        if (!ribbon.gradient) {
            var gradient = ctx.createLinearGradient(0, 0, w, 0);
            for (var c = 0; c < COLORS.length; c += 1) {
                var rgb = COLORS[(c + ribbon.shift) % COLORS.length];
                gradient.addColorStop(c / (COLORS.length - 1), "rgb(" + rgb + ")");
            }
            ribbon.gradient = gradient;
        }
        var width = ribbon.spec[4];
        var alpha = ribbon.spec[5];
        var strands = ribbon.spec[6] || 1;
        for (var p = 0; p < PASSES.length; p += 1) {
            var pass = PASSES[p];
            var copies = pass[3] ? strands : 1;
            ctx.strokeStyle = pass[2] ? "#ffffff" : ribbon.gradient;
            ctx.lineWidth = Math.max(0.5, width * pass[0]);
            for (var s = 0; s < copies; s += 1) {
                // Side strands fan out along the band and fade a little.
                var shift = (s - (copies - 1) / 2) * STRAND_GAP;
                ctx.globalAlpha = alpha * pass[1] * (s === (copies - 1) / 2 ? 1 : 0.6);
                this.trace(pts, shift);
                ctx.stroke();
            }
        }
    };

    Layer.prototype.trace = function (pts, shift) {
        var ctx = this.ctx;
        ctx.beginPath();
        ctx.moveTo(pts[0], pts[1] + shift);
        for (var k = 1; k < SEGMENTS - 1; k += 1) {
            var fan = shift * (0.5 + 0.5 * Math.sin((Math.PI * k) / SEGMENTS));
            ctx.quadraticCurveTo(
                pts[k * 2],
                pts[k * 2 + 1] + fan,
                (pts[k * 2] + pts[k * 2 + 2]) / 2,
                (pts[k * 2 + 1] + pts[k * 2 + 3]) / 2 + fan
            );
        }
        ctx.lineTo(pts[SEGMENTS * 2 - 2], pts[SEGMENTS * 2 - 1] + shift);
    };

    Layer.prototype.drawParticles = function (t, dt, scrolls) {
        var ctx = this.ctx;
        var w = this.w;
        var h = this.h;
        for (var i = 0; i < this.particles.length; i += 1) {
            var p = this.particles[i];
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            if (p.y < -p.r * 2) {
                p.y = h + p.r * 2;
                p.x = rand(0, w);
            }
            if (p.x < -p.r * 2) {
                p.x = w + p.r;
            } else if (p.x > w + p.r * 2) {
                p.x = -p.r;
            }
            var y = p.y;
            if (scrolls) {
                y = (((p.y - scrollY * p.depth) % (h + 40)) + h + 40) % (h + 40) - 20;
            }
            // Drift slightly away from the cursor, easing in and out.
            var dx = p.x - this.px;
            var dy = y - this.py;
            var distance = Math.sqrt(dx * dx + dy * dy) || 1;
            var tx = 0;
            var ty = 0;
            if (distance < REPEL_RADIUS) {
                var force = (1 - distance / REPEL_RADIUS) * REPEL_MAX;
                tx = (dx / distance) * force;
                ty = (dy / distance) * force;
            }
            p.ox += (tx - p.ox) * REPEL_LERP;
            p.oy += (ty - p.oy) * REPEL_LERP;
            ctx.globalAlpha = p.a * (0.55 + 0.45 * Math.sin(t * p.tw + p.ph));
            ctx.drawImage(sprites[p.c], p.x + p.ox - p.r * 2, y + p.oy - p.r * 2, p.r * 4, p.r * 4);
        }
    };

    Layer.prototype.track = function () {
        if (rectsDirty || !this.rect) {
            this.rect = this.canvas.getBoundingClientRect();
        }
        var rect = this.rect;
        if (pointer.on && rect.width) {
            this.px = (pointer.sx - rect.left) * (this.w / rect.width);
            this.py = (pointer.sy - rect.top) * (this.h / rect.height);
        } else {
            this.px = this.py = -1e4;
        }
        // Mouse parallax: each layer drifts by its own depth.
        this.ox += (pointer.nx * this.config.depth - this.ox) * 0.05;
        this.oy += (pointer.ny * this.config.depth * 0.6 - this.oy) * 0.05;
    };

    Layer.prototype.begin = function () {
        var ctx = this.ctx;
        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = 1;
        ctx.clearRect(0, 0, this.w, this.h);
        ctx.translate(this.ox, this.oy);
        ctx.globalCompositeOperation = "lighter";
    };

    Layer.prototype.draw = function (t, dt) {
        if (!this.w) {
            return;
        }
        this.track();
        this.begin();
        for (var i = 0; i < this.ribbons.length; i += 1) {
            this.drawRibbon(this.ribbons[i], t);
        }
        this.drawParticles(t, dt, false);
    };

    // Fixed page background: aurora blobs, section ribbons, particles, trail.
    function AmbientLayer(canvas) {
        Layer.call(this, canvas, { ribbons: [], particles: [64, 26], depth: 6, bokeh: true }, 1.5);
        this.aurora = document.createElement("canvas");
        this.auroraCtx = this.aurora.getContext("2d");
        this.auroraTick = 0;
    }

    AmbientLayer.prototype = Object.create(Layer.prototype);

    AmbientLayer.prototype.resize = function (force) {
        Layer.prototype.resize.call(this, force);
        this.aurora.width = Math.max(8, Math.ceil(this.w / 10));
        this.aurora.height = Math.max(8, Math.ceil(this.h / 10));
        this.anchor();
    };

    // One ribbon on each section edge, so light flows from section to section.
    AmbientLayer.prototype.anchor = function () {
        var sections = document.querySelectorAll("main > section");
        var ribbons = [];
        for (var i = 1; i < sections.length; i += 1) {
            var edge = sections[i].getBoundingClientRect().top + window.scrollY;
            var tilt = (i % 2 ? 1 : -1) * rand(50, 110);
            var ribbon = makeRibbon(
                [edge - tilt, edge + tilt, rand(-90, 90), rand(22, 40), rand(1.4, 2), 0.7, 2],
                i
            );
            ribbon.scroll = 1;
            ribbons.push(ribbon);
        }
        this.ribbons = ribbons;
    };

    AmbientLayer.prototype.drawAurora = function (t) {
        var ctx = this.auroraCtx;
        var w = this.aurora.width;
        var h = this.aurora.height;
        if (this.auroraTick % 3 === 0) {
            ctx.globalCompositeOperation = "source-over";
            ctx.clearRect(0, 0, w, h);
            ctx.globalCompositeOperation = "lighter";
            for (var k = 0; k < COLORS.length; k += 1) {
                var cx = w * (0.5 + 0.4 * Math.sin(t * 0.06 * (k + 1) + k * 2.1));
                var cy = h * (0.5 + 0.42 * Math.cos(t * 0.045 * (k + 1.3) + k));
                var radius = Math.max(w, h) * 0.55;
                var blob = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
                blob.addColorStop(0, "rgba(" + COLORS[k] + ",0.2)");
                blob.addColorStop(1, "rgba(" + COLORS[k] + ",0)");
                ctx.fillStyle = blob;
                ctx.fillRect(0, 0, w, h);
            }
        }
        this.auroraTick += 1;
        this.ctx.globalCompositeOperation = "source-over";
        this.ctx.globalAlpha = 1;
        this.ctx.drawImage(this.aurora, -this.ox, -this.oy, this.w, this.h);
        this.ctx.globalCompositeOperation = "lighter";
    };

    AmbientLayer.prototype.drawTrail = function (dt) {
        var ctx = this.ctx;
        for (var i = trail.length - 1; i >= 0; i -= 1) {
            var dot = trail[i];
            dot.life -= dt * 2.4;
            if (dot.life <= 0) {
                trail.splice(i, 1);
                continue;
            }
            var size = 26 * dot.life;
            ctx.globalAlpha = 0.45 * dot.life;
            ctx.drawImage(sprites[i % COLORS.length], dot.x - this.ox - size / 2, dot.y - this.oy - size / 2, size, size);
        }
    };

    AmbientLayer.prototype.draw = function (t, dt) {
        if (!this.w) {
            return;
        }
        this.track();
        this.begin();
        this.drawAurora(t);
        for (var i = 0; i < this.ribbons.length; i += 1) {
            this.drawRibbon(this.ribbons[i], t);
        }
        this.drawParticles(t, dt, true);
        if (!lite && trail.length) {
            this.drawTrail(dt);
        }
    };

    function Field(name, layers) {
        this.name = name;
        this.layers = layers;
        this.active = true;
        this.frames = 0;
    }

    Field.prototype.resize = function (force) {
        for (var i = 0; i < this.layers.length; i += 1) {
            this.layers[i].resize(force);
        }
    };

    Field.prototype.draw = function (t, dt) {
        for (var i = 0; i < this.layers.length; i += 1) {
            this.layers[i].draw(t, dt);
        }
        this.frames += 1;
    };

    function degrade() {
        lite = true;
        trail.length = 0;
        document.documentElement.classList.add("ql-lite");
        fields.forEach(function (field) {
            field.layers.forEach(function (layer) {
                layer.particles.length = Math.ceil(layer.particles.length / 2);
            });
        });
    }

    function measure(dt) {
        if (lite) {
            return;
        }
        warmup += 1;
        if (warmup < 60) {
            return;
        }
        samples.push(dt);
        if (samples.length === 30) {
            var total = samples.reduce(function (sum, value) {
                return sum + value;
            }, 0);
            samples = [];
            if (total / 30 > FRAME_BUDGET_MS) {
                degrade();
            }
        }
    }

    function tick(now) {
        frameId = 0;
        var dt = lastTime ? now - lastTime : 16.7;
        lastTime = now;
        if (dt > 250) {
            dt = 16.7;
        }
        scrollY = window.scrollY;
        pointer.sx += (pointer.x - pointer.sx) * 0.2;
        pointer.sy += (pointer.y - pointer.sy) * 0.2;
        var running = false;
        var t = now / 1000;
        for (var i = 0; i < fields.length; i += 1) {
            if (fields[i].active) {
                fields[i].draw(t, dt / 1000);
                running = true;
            }
        }
        rectsDirty = false;
        if (running) {
            measure(dt);
        }
        if (running && enabled && !document.hidden) {
            frameId = window.requestAnimationFrame(tick);
        } else {
            lastTime = 0;
        }
    }

    function wake() {
        if (!frameId && enabled && !document.hidden) {
            lastTime = 0;
            warmup = 0;
            samples = [];
            frameId = window.requestAnimationFrame(tick);
        }
    }

    function stop() {
        if (frameId) {
            window.cancelAnimationFrame(frameId);
            frameId = 0;
        }
        lastTime = 0;
    }

    function register(name, layers) {
        if (byName[name]) {
            return byName[name];
        }
        sprites = sprites || makeSprites();
        var field = new Field(name, layers);
        field.resize(true);
        fields.push(field);
        byName[name] = field;
        wake();
        return field;
    }

    function refresh(force) {
        rectsDirty = true;
        fields.forEach(function (field) {
            field.resize(force);
            field.layers.forEach(function (layer) {
                if (layer.anchor) {
                    layer.anchor();
                }
            });
        });
    }

    function startAmbient() {
        var canvas = document.getElementById("ql-ambient");
        if (enabled && canvas) {
            register("ambient", [new AmbientLayer(canvas)]);
        }
    }

    var resizeTimer = 0;
    window.addEventListener("resize", function () {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(function () {
            refresh(false);
        }, 150);
    });
    window.addEventListener("load", function () {
        refresh(false);
    });
    window.addEventListener(
        "scroll",
        function () {
            rectsDirty = true;
        },
        { passive: true }
    );
    window.addEventListener(
        "pointermove",
        function (event) {
            pointer.x = event.clientX;
            pointer.y = event.clientY;
            if (!pointer.on) {
                pointer.sx = pointer.x;
                pointer.sy = pointer.y;
            }
            pointer.on = true;
            pointer.nx = (event.clientX / window.innerWidth - 0.5) * 2;
            pointer.ny = (event.clientY / window.innerHeight - 0.5) * 2;
            if (event.pointerType === "mouse" && fineQuery.matches && !lite && frameId) {
                trail.push({ x: event.clientX, y: event.clientY, life: 1 });
                if (trail.length > 18) {
                    trail.shift();
                }
            }
        },
        { passive: true }
    );

    function release() {
        pointer.on = false;
        pointer.nx = 0;
        pointer.ny = 0;
    }

    document.documentElement.addEventListener("pointerleave", release);
    window.addEventListener("pointerup", function (event) {
        if (event.pointerType !== "mouse") {
            release();
        }
    });
    window.addEventListener("pointercancel", release);
    document.addEventListener("visibilitychange", function () {
        if (document.hidden) {
            stop();
        } else {
            wake();
        }
    });
    reduceQuery.addEventListener("change", function () {
        enabled = !reduceQuery.matches;
        if (enabled) {
            startAmbient();
            wake();
        } else {
            stop();
        }
    });

    window.QLAmbient = {
        get enabled() {
            return enabled;
        },
        frames: function (name) {
            return byName[name] ? byName[name].frames : 0;
        },
        scene: function (name, back, front) {
            if (!enabled || !back || !front) {
                return null;
            }
            var config = SCENES[name === "hero" && isSmall() ? "hero-mobile" : name];
            return register(name, [new Layer(back, config.back, 2), new Layer(front, config.front, 2)]);
        },
        setActive: function (name, active) {
            if (byName[name]) {
                byName[name].active = active;
                if (active) {
                    rectsDirty = true;
                    wake();
                }
            }
        },
        refresh: refresh,
    };

    startAmbient();
})();
