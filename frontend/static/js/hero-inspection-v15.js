(function () {
  const hero = document.querySelector('.hero');
  const light = document.getElementById('carInspectionLight');
  if (!hero || !light) return;
  if (!window.matchMedia('(hover:hover) and (pointer:fine)').matches) return;
  if (window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;

  let frame = 0;
  let x = 70;
  let y = 48;
  hero.addEventListener('pointermove', event => {
    const rect = hero.getBoundingClientRect();
    x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
    y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
    hero.classList.add('inspecting-car');
    if (!frame) frame = requestAnimationFrame(() => {
      light.style.setProperty('--inspect-x', `${x}%`);
      light.style.setProperty('--inspect-y', `${y}%`);
      frame = 0;
    });
  });
  hero.addEventListener('pointerleave', () => hero.classList.remove('inspecting-car'));
})();
