(() => {
  const map = document.querySelector('.quality-map');
  if (!map) return;
  const SVG = 'http://www.w3.org/2000/svg';
  const regions = [...map.querySelectorAll('.heart-segment')];
  const labels = [...map.querySelectorAll('.heart-label')];
  const labelFor = region => map.querySelector(`.heart-label[data-position="${region.dataset.position}"]`);
  const center = map.querySelector('.heart-center');
  const lines = [...map.querySelectorAll('.heart-center-line')];
  const score = map.querySelector('.heart-center-score');
  const band = map.querySelector('.heart-center-band');
  const message = map.querySelector('.heart-center-message');
  const read = id => { try { return JSON.parse(document.getElementById(id).textContent); } catch (error) { return {}; } };
  const messages = read('map-band-messages');
  const colors = read('map-band-colors');
  const original = {
    lines: lines.map(line => line.textContent), score: score.dataset.count, band: band.textContent,
    color: band.getAttribute('fill'), message: [...message.children].map(line => line.textContent),
  };
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const gsap = window.gsap;
  let intro;
  let selected = null;
  let shown = null;
  // Interaction during the entrance used to kill the intro tweens (overwrite: true)
  // and leave segments stuck invisible; finish the intro first, then only
  // overwrite the property being animated.
  const finishIntro = () => { if (intro && intro.progress() < 1) intro.progress(1); };
  const animate = (target, from, to) => { if (gsap && !motion.matches) { finishIntro(); gsap.fromTo(target, from, {...to, duration: .22, overwrite: 'auto'}); } };
  function setMessage(texts) {
    message.replaceChildren(...texts.map((text, index) => {
      const line = document.createElementNS(SVG, 'tspan');
      line.setAttribute('x', '500');
      line.setAttribute('dy', index ? '16' : '0');
      line.textContent = text;
      return line;
    }));
  }
  function setCenter(texts, value, bandName, color, note) {
    lines.forEach((line, index) => { line.textContent = texts[index] || ''; });
    score.textContent = value;
    band.textContent = bandName;
    band.dataset.band = bandName;
    band.setAttribute('fill', color);
    setMessage(note);
  }
  function display(region) {
    finishIntro();
    regions.forEach(item => {
      const active = item === region;
      const muted = Boolean(region && !active);
      item.classList.toggle('is-active', active);
      item.classList.toggle('is-muted', muted);
      labelFor(item).classList.toggle('is-muted', muted);
      item.setAttribute('aria-pressed', String(active));
    });
    if (region === shown) return;
    shown = region;
    if (region) {
      const name = region.dataset.band;
      setCenter([region.dataset.line1, region.dataset.line2], region.dataset.score, name, colors[name] || original.color, messages[name] || []);
    } else {
      setCenter(original.lines, original.score, original.band, original.color, original.message);
    }
    animate(center, {opacity: .35}, {opacity: 1});
  }
  function reset() { selected = null; display(null); }
  regions.forEach(region => {
    region.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') display(region); });
    region.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') display(selected); });
    region.addEventListener('focus', () => display(region));
    region.addEventListener('blur', () => { if (!selected) display(null); });
    region.addEventListener('click', () => { selected = selected === region ? null : region; display(selected); });
    region.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selected = selected === region ? null : region; display(selected); }
      if (event.key === 'Escape') reset();
    });
  });
  map.querySelector('.quality-map-reset').addEventListener('click', reset);
  document.addEventListener('pointerdown', event => { if (!event.target.closest('.heart-segment')) reset(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') reset(); });
  motion.addEventListener('change', () => {
    if (motion.matches && gsap) {
      if (intro) intro.progress(1).kill();
      gsap.killTweensOf([...regions, ...labels, center]);
      gsap.set([...regions, ...labels, center], {clearProps: 'all'});
    }
  });
  if (gsap && !motion.matches) {
    intro = gsap.timeline({defaults: {ease: 'power2.out'}});
    intro.from('.map-heart', {opacity: 0, y: 10, duration: .35, clearProps: 'all'})
      .from(regions, {opacity: 0, stagger: .07, duration: .4, clearProps: 'all'}, .1)
      .from(labels, {opacity: 0, stagger: .07, duration: .4, clearProps: 'all'}, .1)
      .from('.map-panel', {opacity: 0, y: 10, stagger: .08, duration: .35, clearProps: 'all'}, .5);
    // Scores count up to the persisted value (already in the HTML without JS).
    map.querySelectorAll('[data-count]').forEach(counter => {
      const state = {value: 0};
      counter.textContent = '0';
      intro.to(state, {
        value: Number(counter.dataset.count), duration: .9, ease: 'power1.out',
        onUpdate: () => { counter.textContent = String(Math.round(state.value)); },
      }, .2);
    });
  }
})();
