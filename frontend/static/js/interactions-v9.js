(function () {
  const pad = value => String(value).padStart(2, '0');
  const localDay = date => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

  async function loadHeroSlots() {
    const list = document.getElementById('heroSlotsList');
    const dayLabel = document.getElementById('heroSlotsDay');
    if (!list || typeof api !== 'function') return;
    for (let offset = 0; offset < 4; offset += 1) {
      const date = new Date();
      date.setDate(date.getDate() + offset);
      const day = localDay(date);
      try {
        const data = await api(`/bookings/slots?day=${encodeURIComponent(day)}`);
        const now = new Date();
        const free = data.slots.filter(slot => slot.available && new Date(`${day}T${slot.time}:00`) > now).slice(0, 4);
        if (!free.length) continue;
        dayLabel.textContent = offset === 0 ? 'сегодня' : new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'short' }).format(date);
        list.innerHTML = free.map(slot => `<button type="button" data-hero-day="${day}" data-hero-time="${slot.time}">${slot.time}</button>`).join('');
        return;
      } catch (_) {}
    }
    list.innerHTML = '<span style="font-size:12px;color:#9aa5ad">Уточним удобное время по телефону</span>';
  }

  document.addEventListener('click', event => {
    const slot = event.target.closest('[data-hero-time]');
    if (slot && typeof openBooking === 'function') {
      openBooking();
      setTimeout(() => {
        const dayButton = document.querySelector(`#bookingDays [data-day="${slot.dataset.heroDay}"]`);
        if (dayButton && typeof selectBookingDay === 'function') {
          selectBookingDay(slot.dataset.heroDay, dayButton).then(() => {
            const timeButton = document.querySelector(`#bookingSlots [data-time="${slot.dataset.heroTime}"]:not(:disabled)`);
            if (timeButton) timeButton.click();
          });
        }
      }, 80);
    }
  });

  function setCompare(slider, clientX) {
    const rect = slider.getBoundingClientRect();
    const value = Math.max(2, Math.min(98, ((clientX - rect.left) / rect.width) * 100));
    slider.style.setProperty('--split', `${value}%`);
    slider.querySelector('.compare-handle')?.setAttribute('aria-valuenow', String(Math.round(value)));
  }
  document.querySelectorAll('[data-compare]').forEach(slider => {
    let active = false;
    slider.addEventListener('pointerdown', event => { active = true; slider.setPointerCapture(event.pointerId); setCompare(slider, event.clientX); });
    slider.addEventListener('pointermove', event => { if (active) setCompare(slider, event.clientX); });
    slider.addEventListener('pointerup', () => { active = false; });
    slider.querySelector('.compare-handle')?.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const current = parseInt(slider.querySelector('.compare-handle').getAttribute('aria-valuenow') || '50', 10);
      const next = Math.max(0, Math.min(100, current + (event.key === 'ArrowRight' ? 5 : -5)));
      slider.style.setProperty('--split', `${next}%`);
      slider.querySelector('.compare-handle').setAttribute('aria-valuenow', String(next));
    });
  });

  function bindChoiceGroup(id) {
    document.getElementById(id)?.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;
      button.parentElement.querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
      if (typeof renderGoalRecommendation === 'function') {
        const goal = document.querySelector('#goalButtons button.active')?.dataset.goal || 'inside';
        renderGoalRecommendation(goal);
      }
      if (navigator.vibrate) navigator.vibrate(6);
    });
  }
  bindChoiceGroup('vehicleButtons');
  bindChoiceGroup('priorityButtons');
  const hero = document.querySelector('.hero');
  if (hero && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const ring = document.createElement('span');
    ring.className = 'pointer-water';
    ring.setAttribute('aria-hidden', 'true');
    hero.appendChild(ring);
    let timer = 0;
    hero.addEventListener('pointerdown', event => {
      if (event.target.closest('a,button,input,select')) return;
      const rect = hero.getBoundingClientRect();
      hero.style.setProperty('--px', `${event.clientX - rect.left}px`);
      hero.style.setProperty('--py', `${event.clientY - rect.top}px`);
      hero.classList.remove('water-touch');
      void ring.offsetWidth;
      hero.classList.add('water-touch');
      clearTimeout(timer);
      timer = setTimeout(() => hero.classList.remove('water-touch'), 900);
    });
  }
  loadHeroSlots();
  window.setInterval(loadHeroSlots, 120000);

  window.celebratePineapple = function (anchor) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const rect = anchor?.getBoundingClientRect() || { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
    for (let index = 0; index < 18; index += 1) {
      const piece = document.createElement('span');
      piece.className = 'pineapple-confetti';
      piece.textContent = index % 3 ? '✦' : '🍍';
      piece.style.setProperty('--x', `${rect.left + rect.width / 2}px`);
      piece.style.setProperty('--y', `${rect.top + Math.min(rect.height / 2, 160)}px`);
      piece.style.setProperty('--dx', `${(Math.random() - .5) * 300}px`);
      piece.style.setProperty('--dy', `${-60 - Math.random() * 240}px`);
      piece.style.setProperty('--r', `${(Math.random() - .5) * 420}deg`);
      piece.style.setProperty('--s', `${10 + Math.random() * 15}px`);
      document.body.appendChild(piece);
      setTimeout(() => piece.remove(), 1400);
    }
  };
})();
