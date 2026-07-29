(function () {
  const hero = document.querySelector('.hero');
  const range = document.getElementById('washRange');
  const replay = document.getElementById('washReplay');
  if (!hero || !range) return;

  let animationFrame = 0;
  let current = Number(range.value) || 0;
  let userTouched = false;

  function paint(value, active = false) {
    current = Math.max(0, Math.min(100, value));
    range.value = String(Math.round(current));
    hero.style.setProperty('--wash', `${current}%`);
    hero.style.setProperty('--wash-active', active ? '1' : '0');
    hero.classList.toggle('is-washing', active);
  }

  function stop() {
    cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    hero.style.setProperty('--wash-active', '0');
    hero.classList.remove('is-washing');
  }

  function play(from = 0) {
    stop();
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) { paint(100, false); return; }
    const started = performance.now();
    const duration = 3400;
    function tick(now) {
      const linear = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - linear, 3);
      paint(from + (100 - from) * eased, linear < 1);
      if (linear < 1) animationFrame = requestAnimationFrame(tick);
      else stop();
    }
    animationFrame = requestAnimationFrame(tick);
  }

  range.addEventListener('pointerdown', () => { userTouched = true; stop(); });
  range.addEventListener('input', () => paint(Number(range.value), true));
  range.addEventListener('change', () => {
    hero.style.setProperty('--wash-active', '0');
    hero.classList.remove('is-washing');
  });
  replay?.addEventListener('click', () => { userTouched = true; paint(0, true); play(0); });

  paint(0, false);
  window.setTimeout(() => { if (!userTouched) play(0); }, 650);
})();
