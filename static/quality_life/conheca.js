/* "Conheça a Quality" (docs/specs/16-conheca-a-quality.md).
   - Hero background: a small WebGL noise gradient in the brand colors.
   - Ring logo as a 3D coin (three.js r128): tilts toward the pointer, drag to
     spin, tap to flip; three glossy spheres from the logo's figures orbit it.
   - GSAP + ScrollTrigger: word reveals, parallax lights, giant type rows,
     the steps rail drawing with the scroll.
   Without WebGL the plain logo image stays (data-state="image"); without GSAP
   or with prefers-reduced-motion: reduce nothing is hidden and nothing moves
   on its own. Purely visual: no data is read or sent. */
(() => {
    'use strict';
    const root = document.getElementById('qlc');
    if (!root) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    const G = window.gsap || null;
    const ST = window.ScrollTrigger || null;
    if (G && ST) G.registerPlugin(ST);
    const hero = document.getElementById('qlc-hero');
    const stage = document.getElementById('qlc-logo3d');
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    // intro/spin belong to the entrance, scale/scroll to the scroll, flip/drag to the hand:
    // separate properties so the tweens never record each other's values.
    const coinState = { rx: 0, ry: 0, flip: 0, spin: 0, intro: 1, scroll: 0, scale: 1, drag: 0 };

    function webglAvailable() {
        try {
            const probe = document.createElement('canvas');
            return Boolean(probe.getContext('webgl') || probe.getContext('experimental-webgl'));
        } catch (error) {
            return false;
        }
    }
    const hasWebGL = webglAvailable();

    /* Animated gradient behind the hero ---------------------------------------- */
    function initBackground() {
        const canvas = document.getElementById('qlc-bg');
        let gl = null;
        try { gl = canvas.getContext('webgl', { antialias: false, alpha: false }); } catch (error) { gl = null; }
        if (!gl) return null;
        const vertex = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}';
        const fragment = [
            'precision mediump float;uniform vec2 r;uniform float t;uniform vec2 m;',
            'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
            'float n(vec2 p){vec2 i=floor(p),f=fract(p);vec2 u=f*f*(3.-2.*f);',
            'return mix(mix(h(i),h(i+vec2(1,0)),u.x),mix(h(i+vec2(0,1)),h(i+1.),u.x),u.y);}',
            'float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}',
            'void main(){vec2 uv=gl_FragCoord.xy/r;vec2 p=(gl_FragCoord.xy-.5*r)/r.y;p+=m*.12;float T=t*.045;',
            'vec2 q=vec2(fbm(p*1.3+T),fbm(p*1.3-T+3.1));float f=fbm(p*1.5+q*1.9+vec2(T*2.,-T));',
            'vec3 base=vec3(.024,.078,.098);vec3 teal=vec3(.05,.42,.39);vec3 mag=vec3(.70,.13,.46);',
            'vec3 org=vec3(.86,.43,.06);vec3 plum=vec3(.40,.27,.58);',
            'vec3 c=base;c=mix(c,teal,smoothstep(.38,.86,f)*.55);c=mix(c,plum,smoothstep(.42,.9,q.x)*.4);',
            'c=mix(c,mag,smoothstep(.5,.95,q.y*f*1.7)*.5);c=mix(c,org,smoothstep(.6,1.,f*q.x*2.)*.42);',
            'float v=smoothstep(1.3,.15,length(p-vec2(.45,.05)));c=mix(base,c,.3+.7*v);',
            'c=mix(c,base,smoothstep(.0,.9,1.-uv.y)*.35);',
            'c+=(h(gl_FragCoord.xy+fract(t))-.5)*.03;gl_FragColor=vec4(c,1.);}',
        ].join('\n');
        const shader = (type, source) => {
            const object = gl.createShader(type);
            gl.shaderSource(object, source);
            gl.compileShader(object);
            return object;
        };
        const program = gl.createProgram();
        gl.attachShader(program, shader(gl.VERTEX_SHADER, vertex));
        gl.attachShader(program, shader(gl.FRAGMENT_SHADER, fragment));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
        gl.useProgram(program);
        gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
        const location = gl.getAttribLocation(program, 'a');
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
        const uR = gl.getUniformLocation(program, 'r');
        const uT = gl.getUniformLocation(program, 't');
        const uM = gl.getUniformLocation(program, 'm');
        const size = () => {
            const scale = 0.55 * Math.min(window.devicePixelRatio || 1, 1.5);
            canvas.width = Math.max(2, Math.floor(canvas.clientWidth * scale));
            canvas.height = Math.max(2, Math.floor(canvas.clientHeight * scale));
            gl.viewport(0, 0, canvas.width, canvas.height);
        };
        size();
        return {
            size,
            draw(time) {
                gl.uniform2f(uR, canvas.width, canvas.height);
                gl.uniform1f(uT, time);
                gl.uniform2f(uM, pointer.x, -pointer.y);
                gl.drawArrays(gl.TRIANGLES, 0, 3);
            },
        };
    }

    /* Ring logo as a 3D coin ------------------------------------------------------ */
    function initCoin() {
        const T = window.THREE;
        if (!T) return null;
        const canvas = document.getElementById('qlc-coin');
        let renderer;
        try {
            renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
        } catch (error) {
            return null;
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.outputEncoding = T.sRGBEncoding;
        renderer.toneMapping = T.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.0;
        const scene = new T.Scene();
        const camera = new T.PerspectiveCamera(30, 1, 0.1, 60);
        camera.position.set(0, 0, 7.4);

        // Small studio for glossy reflections.
        const pmrem = new T.PMREMGenerator(renderer);
        const studio = new T.Scene();
        studio.add(new T.Mesh(new T.SphereGeometry(12, 32, 16), new T.MeshBasicMaterial({ color: 0x071a20, side: T.BackSide })));
        const panel = (hex, power, x, y, z, w, h) => {
            const mesh = new T.Mesh(
                new T.PlaneGeometry(w, h),
                new T.MeshBasicMaterial({ color: new T.Color(hex).multiplyScalar(power), side: T.DoubleSide }),
            );
            mesh.position.set(x, y, z);
            mesh.lookAt(0, 0, 0);
            studio.add(mesh);
        };
        panel('#ffffff', 3.2, 0, 5, 5, 8, 2.4);
        panel('#e0359f', 2.2, 6, 0, 1, 3, 6);
        panel('#4fd8ca', 2.0, -6, -1, 2, 3, 6);
        panel('#f98c16', 1.8, 0, -5, 3, 7, 1.6);
        panel('#ffffff', 1.2, 0, 2, -6, 6, 3);
        scene.environment = pmrem.fromScene(studio, 0.035).texture;

        scene.add(new T.AmbientLight(0xffffff, 0.22));
        const key = new T.DirectionalLight(0xffffff, 1.25);
        key.position.set(3, 4, 6);
        scene.add(key);
        const pink = new T.PointLight(0xe0359f, 1.6, 14);
        pink.position.set(-3.5, -1.5, 3);
        scene.add(pink);
        const teal = new T.PointLight(0x4fd8ca, 1.3, 14);
        teal.position.set(3.5, -2, 2.5);
        scene.add(teal);

        const linear = hex => new T.Color(hex).convertSRGBToLinear();
        const group = new T.Group();
        const coin = new T.Group();
        scene.add(group);
        group.add(coin);

        const texture = new T.TextureLoader().load(stage.dataset.logo, () => {
            stage.dataset.state = '3d';
            if (reduce) requestFrame();
        });
        texture.encoding = T.sRGBEncoding;
        texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
        // Show the white disc only; the painted ring becomes the 3D rim.
        texture.repeat.set(0.9, 0.9);
        texture.offset.set(0.05, 0.05);
        const face = new T.MeshPhysicalMaterial({
            map: texture, roughness: 0.3, metalness: 0, clearcoat: 0.8, clearcoatRoughness: 0.12, envMapIntensity: 0.55,
        });
        const front = new T.Mesh(new T.CircleGeometry(0.95, 128), face);
        front.position.z = 0.095;
        coin.add(front);
        const back = new T.Mesh(new T.CircleGeometry(0.95, 128), face);
        back.position.z = -0.095;
        back.rotation.y = Math.PI;
        coin.add(back);
        const side = new T.CylinderGeometry(0.95, 0.95, 0.19, 128, 1, true);
        side.rotateX(Math.PI / 2);
        coin.add(new T.Mesh(side, new T.MeshPhysicalMaterial({ color: linear('#f4f1f3'), roughness: 0.35, clearcoat: 0.6 })));

        // Rim: the logo's orange → magenta → purple ring, clockwise from the top.
        const rim = new T.TorusGeometry(1, 0.115, 48, 260);
        const positions = rim.attributes.position;
        const colors = new Float32Array(positions.count * 3);
        const stops = [
            [0, '#f98c16'], [0.16, '#f2624f'], [0.3, '#cb2ba1'], [0.5, '#ac2d84'],
            [0.66, '#7f5aa8'], [0.8, '#a37fa0'], [0.92, '#f49e27'], [1, '#f98c16'],
        ].map(([at, hex]) => [at, linear(hex)]);
        const mixed = new T.Color();
        for (let i = 0; i < positions.count; i += 1) {
            let u = (Math.PI / 2 - Math.atan2(positions.getY(i), positions.getX(i))) / (2 * Math.PI);
            u -= Math.floor(u);
            for (let k = 0; k < stops.length - 1; k += 1) {
                if (u >= stops[k][0] && u <= stops[k + 1][0]) {
                    mixed.copy(stops[k][1]).lerp(stops[k + 1][1], (u - stops[k][0]) / (stops[k + 1][0] - stops[k][0]));
                    break;
                }
            }
            colors[i * 3] = mixed.r;
            colors[i * 3 + 1] = mixed.g;
            colors[i * 3 + 2] = mixed.b;
        }
        rim.setAttribute('color', new T.BufferAttribute(colors, 3));
        coin.add(new T.Mesh(rim, new T.MeshPhysicalMaterial({
            vertexColors: true, roughness: 0.2, metalness: 0.08, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 0.45,
        })));

        // The three figures of the logo, as glossy spheres in orbit.
        const spheres = [['#7b2d8e', 0], ['#16b3a6', 2.094], ['#a8c43a', 4.189]].map(([hex, phase]) => {
            const mesh = new T.Mesh(
                new T.SphereGeometry(0.15, 48, 32),
                new T.MeshPhysicalMaterial({ color: linear(hex), roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 0.9 }),
            );
            mesh.userData.phase = phase;
            group.add(mesh);
            return mesh;
        });

        // Sparkles.
        const count = 160;
        const sparkGeometry = new T.BufferGeometry();
        const sparkPositions = new Float32Array(count * 3);
        const sparkColors = new Float32Array(count * 3);
        const palette = ['#f98c16', '#e0359f', '#4fd8ca', '#b89cf0'].map(linear);
        for (let j = 0; j < count; j += 1) {
            const radius = 1.5 + Math.random() * 1.1;
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            sparkPositions[j * 3] = radius * Math.sin(phi) * Math.cos(theta);
            sparkPositions[j * 3 + 1] = radius * Math.cos(phi) * 0.8;
            sparkPositions[j * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
            const color = palette[j % palette.length];
            sparkColors[j * 3] = color.r;
            sparkColors[j * 3 + 1] = color.g;
            sparkColors[j * 3 + 2] = color.b;
        }
        sparkGeometry.setAttribute('position', new T.BufferAttribute(sparkPositions, 3));
        sparkGeometry.setAttribute('color', new T.BufferAttribute(sparkColors, 3));
        const sparks = new T.Points(sparkGeometry, new T.PointsMaterial({
            size: 0.035, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false, blending: T.AdditiveBlending,
        }));
        group.add(sparks);

        const size = () => {
            const width = stage.clientWidth;
            renderer.setSize(width, width, false);
            camera.aspect = 1;
            camera.updateProjectionMatrix();
        };
        size();

        return {
            size,
            render(time) {
                const sway = reduce ? 0 : 1;
                const s = coinState;
                coin.rotation.y = s.ry + s.flip + s.spin + s.scroll + s.drag + Math.sin(time * 0.55) * 0.22 * sway + (reduce ? -0.35 : 0);
                coin.rotation.x = s.rx + Math.sin(time * 0.42) * 0.07 * sway + (reduce ? 0.12 : 0);
                coin.position.y = Math.sin(time * 1.05) * 0.07 * sway;
                group.scale.setScalar(s.scale * s.intro);
                spheres.forEach((sphere, index) => {
                    const angle = time * 0.45 * sway + sphere.userData.phase;
                    sphere.position.set(Math.cos(angle) * 1.58, Math.sin(angle * 1.6) * 0.32 + 0.15 * (index - 1), Math.sin(angle) * 0.95);
                });
                sparks.rotation.y = time * 0.04 * sway;
                sparks.rotation.x = Math.sin(time * 0.2) * 0.1 * sway;
                renderer.render(scene, camera);
            },
        };
    }

    const background = hasWebGL ? initBackground() : null;
    const coin = hasWebGL ? initCoin() : null;
    const hint = document.getElementById('qlc-hint');
    if (coin) hint.hidden = false;

    hero.addEventListener('pointermove', event => {
        const box = hero.getBoundingClientRect();
        pointer.tx = ((event.clientX - box.left) / box.width) * 2 - 1;
        pointer.ty = ((event.clientY - box.top) / box.height) * 2 - 1;
    });
    hero.addEventListener('pointerleave', () => { pointer.tx = 0; pointer.ty = 0; });

    // Drag to spin, tap to flip.
    if (coin) {
        const canvas = document.getElementById('qlc-coin');
        let down = false;
        let startX = 0;
        let base = 0;
        let moved = 0;
        canvas.addEventListener('pointerdown', event => {
            down = true;
            startX = event.clientX;
            base = coinState.drag;
            moved = 0;
            canvas.style.cursor = 'grabbing';
            try { canvas.setPointerCapture(event.pointerId); } catch (error) { /* older WebKit */ }
        });
        canvas.addEventListener('pointermove', event => {
            if (!down) return;
            const dx = event.clientX - startX;
            moved = Math.max(moved, Math.abs(dx));
            coinState.drag = base + dx * 0.012;
            if (reduce) requestFrame();
        });
        const release = () => {
            if (!down) return;
            down = false;
            canvas.style.cursor = '';
            if (moved < 6) {
                if (G && !reduce) G.to(coinState, { flip: coinState.flip + Math.PI * 2, duration: 1.8, ease: 'elastic.out(1, 0.45)' });
                else { coinState.flip += Math.PI; requestFrame(); }
            } else if (G && !reduce) {
                G.to(coinState, { drag: Math.round(coinState.drag / Math.PI) * Math.PI, duration: 1.2, ease: 'elastic.out(1, 0.5)' });
            }
        };
        canvas.addEventListener('pointerup', release);
        canvas.addEventListener('pointercancel', release);
    }

    // Floating tags drift against the pointer (depth parallax).
    const tags = G && !reduce ? [...root.querySelectorAll('.qlc-tagp')].map(element => ({
        depth: Number(element.dataset.depth) || 1,
        x: G.quickTo(element, 'x', { duration: 0.9, ease: 'power3' }),
        y: G.quickTo(element, 'y', { duration: 0.9, ease: 'power3' }),
    })) : [];

    // Render loop, paused while the hero is off screen; one frame on demand with reduced motion.
    let visible = true;
    let running = false;
    const start = performance.now();
    function frame(now) {
        running = false;
        if (!visible) return;
        const time = (now - start) / 1000;
        pointer.x += (pointer.tx - pointer.x) * 0.06;
        pointer.y += (pointer.ty - pointer.y) * 0.06;
        coinState.ry = pointer.x * 0.55;
        coinState.rx = pointer.y * 0.35;
        if (background) background.draw(reduce ? 0 : time);
        if (coin) coin.render(reduce ? 0 : time);
        if (!reduce) {
            tags.forEach(tag => {
                tag.x(pointer.x * -18 * tag.depth);
                tag.y(pointer.y * -14 * tag.depth);
            });
            running = true;
            requestAnimationFrame(frame);
        }
    }
    function requestFrame() {
        if (!running) {
            running = true;
            requestAnimationFrame(frame);
        }
    }
    if ('IntersectionObserver' in window) {
        new IntersectionObserver(entries => {
            visible = entries[0].isIntersecting;
            if (visible) requestFrame();
        }).observe(hero);
    }
    if (background || coin) requestFrame();
    window.addEventListener('resize', () => {
        if (background) background.size();
        if (coin) coin.size();
        requestFrame();
    });

    // Copy the contact e-mail (falls back to selecting it).
    root.querySelectorAll('[data-copy]').forEach(button => {
        button.addEventListener('click', () => {
            const target = document.getElementById(button.dataset.copy);
            const text = target.textContent.trim();
            const select = () => {
                const range = document.createRange();
                range.selectNodeContents(target);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                button.textContent = 'Selecionado';
            };
            const done = () => {
                button.textContent = 'Copiado';
                button.dataset.copied = '';
                setTimeout(() => { button.textContent = 'Copiar'; delete button.dataset.copied; }, 1800);
            };
            try { navigator.clipboard.writeText(text).then(done, select); } catch (error) { select(); }
        });
    });

    // Spotlight that follows the pointer on the solution cards.
    root.querySelectorAll('.qlc-card').forEach(card => {
        card.addEventListener('pointermove', event => {
            const box = card.getBoundingClientRect();
            card.style.setProperty('--mx', `${event.clientX - box.left}px`);
            card.style.setProperty('--my', `${event.clientY - box.top}px`);
        });
    });

    if (!G || reduce) return;

    /* Split a heading into masked words (text nodes word by word, inline
       elements such as the gradient words as one unit). */
    function split(element) {
        const words = [];
        [...element.childNodes].forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                const fragment = document.createDocumentFragment();
                node.textContent.split(/(\s+)/).forEach(part => {
                    if (!part) return;
                    if (/^\s+$/.test(part)) { fragment.appendChild(document.createTextNode(' ')); return; }
                    const outer = document.createElement('span');
                    const inner = document.createElement('span');
                    outer.className = 'qlc-w';
                    inner.className = 'qlc-wi';
                    inner.textContent = part;
                    outer.appendChild(inner);
                    fragment.appendChild(outer);
                    words.push(inner);
                });
                element.replaceChild(fragment, node);
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const outer = document.createElement('span');
                outer.className = 'qlc-w';
                element.replaceChild(outer, node);
                node.classList.add('qlc-wi');
                outer.appendChild(node);
                words.push(node);
            }
        });
        return words;
    }

    // Intro.
    const intro = G.timeline({ defaults: { ease: 'expo.out' } });
    intro.from('.qlc-pill', { y: 24, opacity: 0, duration: 1 })
        .from(split(document.getElementById('qlc-title')), { yPercent: 115, rotate: 4, duration: 1.2, stagger: 0.07 }, '-=0.7')
        .from('.qlc-lead', { y: 26, opacity: 0, duration: 1.1 }, '-=0.85')
        .from('.qlc-cta > *', { y: 22, opacity: 0, stagger: 0.1, duration: 1 }, '-=0.8')
        .from('.qlc-tag', { scale: 0, opacity: 0, stagger: 0.09, duration: 0.9, ease: 'back.out(2.2)' }, '-=1');
    if (coin) G.from(coinState, { intro: 0.15, spin: -Math.PI * 2.5, duration: 2.6, ease: 'expo.out', delay: 0.15 });
    G.from('.qlc-halo', { scale: 0.3, opacity: 0, duration: 2, ease: 'expo.out' });

    if (fine) {
        // Magnetic buttons.
        root.querySelectorAll('[data-magnetic]').forEach(button => {
            const toX = G.quickTo(button, 'x', { duration: 0.6, ease: 'elastic.out(1, 0.35)' });
            const toY = G.quickTo(button, 'y', { duration: 0.6, ease: 'elastic.out(1, 0.35)' });
            button.addEventListener('pointermove', event => {
                const box = button.getBoundingClientRect();
                toX((event.clientX - box.left - box.width / 2) * 0.32);
                toY((event.clientY - box.top - box.height / 2) * 0.45);
            });
            button.addEventListener('pointerleave', () => { toX(0); toY(0); });
        });
        // Cards tilt in 3D under the pointer and spring back.
        root.querySelectorAll('[data-tilt]').forEach(card => {
            G.set(card, { transformPerspective: 900 });
            const toRX = G.quickTo(card, 'rotationX', { duration: 0.7, ease: 'power3' });
            const toRY = G.quickTo(card, 'rotationY', { duration: 0.7, ease: 'power3' });
            card.addEventListener('pointermove', event => {
                const box = card.getBoundingClientRect();
                toRY(((event.clientX - box.left) / box.width - 0.5) * 10);
                toRX(-((event.clientY - box.top) / box.height - 0.5) * 10);
            });
            card.addEventListener('pointerleave', () => { toRX(0); toRY(0); });
        });
    }

    if (!ST) return;
    const scrub = (trigger, start, end) => ({ trigger, start, end, scrub: true });

    // Hero: the coin turns and shrinks, the background drifts.
    if (coin) G.to(coinState, { scroll: Math.PI * 1.25, scale: 0.82, ease: 'none', scrollTrigger: scrub(hero, 'top top', 'bottom top') });
    G.to('#qlc-bg', { yPercent: 12, ease: 'none', scrollTrigger: scrub(hero, 'top top', 'bottom top') });
    G.matchMedia().add('(min-width: 1101px)', () => {
        G.to('.qlc-hero__copy', { y: -90, opacity: 0.2, ease: 'none', scrollTrigger: scrub(hero, 'top top', 'bottom top') });
        G.to('.qlc-logo3d', { y: 80, ease: 'none', scrollTrigger: scrub(hero, 'top top', 'bottom top') });
    });

    // Parallax lights and giant type.
    root.querySelectorAll('.qlc-orb').forEach(orb => {
        const speed = Number(orb.dataset.speed) || 0.4;
        G.fromTo(orb, { y: speed * 220 }, { y: -speed * 220, ease: 'none', scrollTrigger: scrub(orb.closest('.qlc-section'), 'top bottom', 'bottom top') });
    });
    root.querySelectorAll('[data-par]').forEach(element => {
        const distance = Number(element.dataset.par);
        G.fromTo(element, { y: distance }, { y: -distance, ease: 'none', scrollTrigger: scrub(element, 'top bottom', 'bottom top') });
    });
    const bigtype = root.querySelector('.qlc-bigtype');
    G.fromTo('.qlc-bigtype__row--outline', { xPercent: 0 }, { xPercent: -35, ease: 'none', scrollTrigger: scrub(bigtype, 'top bottom', 'bottom top') });
    G.fromTo('.qlc-bigtype__row--warm', { xPercent: -35 }, { xPercent: 0, ease: 'none', scrollTrigger: scrub(bigtype, 'top bottom', 'bottom top') });

    // Reveals.
    root.querySelectorAll('[data-split]').forEach(heading => {
        G.from(split(heading), { yPercent: 115, rotate: 3, duration: 1.1, ease: 'expo.out', stagger: 0.06, scrollTrigger: { trigger: heading, start: 'top 88%' } });
    });
    root.querySelectorAll('[data-up]').forEach(element => {
        G.from(element, { y: 44, opacity: 0, duration: 1.1, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 90%' } });
    });
    root.querySelectorAll('[data-stagger]').forEach(group => {
        G.from(group.children, {
            y: 60, opacity: 0, rotationX: -18, transformPerspective: 900, transformOrigin: '50% 0%',
            duration: 1, ease: 'power4.out', stagger: 0.1, scrollTrigger: { trigger: group, start: 'top 85%' },
        });
    });
    root.querySelectorAll('[data-flip]').forEach(group => {
        G.from(group.children, {
            rotationY: -70, opacity: 0, transformPerspective: 700, transformOrigin: '0% 50%',
            duration: 0.9, ease: 'back.out(1.6)', stagger: 0.07, scrollTrigger: { trigger: group, start: 'top 88%' },
        });
    });
    G.from('[data-pop] > *', { scale: 0.6, opacity: 0, y: 20, duration: 0.8, ease: 'back.out(2)', stagger: 0.08, scrollTrigger: { trigger: '[data-pop]', start: 'top 88%' } });

    // Steps: the rail draws with the scroll.
    const steps = document.getElementById('qlc-steps');
    const rail = G.matchMedia();
    rail.add('(min-width: 861px)', () => {
        G.fromTo('#qlc-railfill', { scaleX: 0, scaleY: 1 }, { scaleX: 1, ease: 'none', scrollTrigger: scrub(steps, 'top 80%', 'bottom 55%') });
    });
    rail.add('(max-width: 860px)', () => {
        G.fromTo('#qlc-railfill', { scaleY: 0, scaleX: 1 }, { scaleY: 1, ease: 'none', scrollTrigger: scrub(steps, 'top 75%', 'bottom 45%') });
    });
    G.from('.qlc-step__n', { scale: 0, duration: 0.8, ease: 'back.out(2.5)', stagger: 0.12, scrollTrigger: { trigger: steps, start: 'top 82%' } });
    G.from('.qlc-step strong', { opacity: 0, y: 14, duration: 0.8, ease: 'power3.out', stagger: 0.12, scrollTrigger: { trigger: steps, start: 'top 82%' } });

    // The contact block grows in.
    G.fromTo('#qlc-contactbox', { scale: 0.92, opacity: 0.6 }, { scale: 1, opacity: 1, ease: 'none', scrollTrigger: scrub('#qlc-contactbox', 'top bottom', 'top 75%') });
})();
