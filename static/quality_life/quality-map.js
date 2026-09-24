(() => {
  const map = document.querySelector('.quality-map');
  if (!map) return;
  const regions = [...map.querySelectorAll('.heart-segment')];
  const name = map.querySelector('.heart-center-name');
  const score = map.querySelector('.heart-center-score');
  const band = map.querySelector('.heart-center-band');
  const original = {name: name.innerHTML, score: score.textContent, band: band.textContent};
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const gsap = window.gsap;
  let intro;
  let selected = null;
  const animate = (target, values) => { if (gsap && !motion.matches) gsap.to(target, {...values, duration: .22, overwrite: true}); };
  function display(region) {
    regions.forEach(item => {
      item.classList.toggle('is-active', item === region);
      item.classList.toggle('is-muted', Boolean(region && item !== region));
      item.setAttribute('aria-pressed', String(item === region));
      animate(item, {scale: item === region ? 1.025 : 1});
    });
    if (region) {
      name.textContent = region.dataset.name;
      score.textContent = region.dataset.score;
      band.textContent = region.dataset.band;
      band.dataset.band = region.dataset.band;
    } else {
      name.innerHTML = original.name;
      score.textContent = original.score;
      band.textContent = original.band;
      band.dataset.band = original.band;
    }
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
  motion.addEventListener('change', () => { if (motion.matches && gsap) { if (intro) intro.progress(1).kill(); gsap.killTweensOf(regions); gsap.set(regions, {clearProps: 'transform,opacity'}); } });
  if (gsap && !motion.matches) {
    intro = gsap.timeline({defaults: {ease: 'power2.out'}});
    intro.from('.map-canvas', {opacity: 0, y: 10, duration: .35})
      .from(regions, {opacity: 0, scale: .98, transformOrigin: '50% 50%', stagger: .055, duration: .4}, .1)
      .from('.heart-center', {opacity: 0, duration: .3}, .65)
      .from('.map-panel', {opacity: 0, y: 10, stagger: .1, duration: .35}, .7);
  }
})();
