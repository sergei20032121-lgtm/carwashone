// ==== НАСТРОЙКА ====
// Адрес backend API. Если открываешь файлы напрямую (file://) или сайт живёт
// на другом домене — поменяй на реальный адрес сервера.
const API_BASE = window.location.origin.startsWith('http')
  ? (window.CARWASH_API_BASE || window.location.origin)
  : 'http://127.0.0.1:8123';

const TOKEN_KEY = 'avtomoyka1_token';
const ROLE_KEY = 'avtomoyka1_role';

function getAuthToken() { return sessionStorage.getItem(TOKEN_KEY); }
function getAuthRole() { return sessionStorage.getItem(ROLE_KEY); }
function setAuthToken(token, role) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token); else sessionStorage.removeItem(TOKEN_KEY);
  if (role) sessionStorage.setItem(ROLE_KEY, role); else sessionStorage.removeItem(ROLE_KEY);
}
function clearAuth() { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(ROLE_KEY); }

async function api(path, options = {}) {
  const headers = options.headers || {};
  headers['Content-Type'] = 'application/json';
  const token = getAuthToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch (e) {}
    const err = new Error(detail || ('HTTP ' + res.status));
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

// Таблицы CRM остаются обычными на десктопе, а на телефоне автоматически
// получают подписи полей и превращаются в карточки. Работает и для строк,
// которые админка добавляет после API-запросов.
function initMobileTableCards() {
  let queued = false;
  const enhance = () => {
    queued = false;
    document.querySelectorAll('table').forEach(table => {
      const labels = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      if (!labels.length) return;
      table.classList.add('mobile-card-table');
      table.querySelectorAll('tbody tr').forEach(row => {
        [...row.children].forEach((cell, index) => {
          if (cell.tagName === 'TD' && !cell.hasAttribute('colspan')) {
            cell.dataset.label = labels[index] || '';
          }
        });
      });
    });
  };
  const schedule = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(enhance);
  };
  schedule();
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMobileTableCards, { once: true });
} else {
  initMobileTableCards();
}

if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js', { scope: './' }).catch(() => {});
  });
}

// ==== Премиальные UI-фичи ====

// Тактильный отклик на мобильных (успешная запись, начисление ананаса и т.п.)
function tactileFeedback(pattern = 10) {
  if (navigator.vibrate) navigator.vibrate(pattern);
}

// Кастомный курсор-капля (десктоп only)
function initCustomCursor() {
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.body.classList.add('custom-cursor-on');
  const cursor = document.createElement('div');
  cursor.className = 'custom-cursor';
  cursor.innerHTML = '<span class="cursor-drop-shape"><span class="cursor-drop-fill"></span><svg viewBox="0 0 24 28" aria-hidden="true"><path d="M12 1.5C16.7 8 21 13.1 21 18a9 9 0 1 1-18 0C3 13.1 7.3 8 12 1.5Z"/></svg></span>';
  document.body.appendChild(cursor);
  const shape = cursor.querySelector('.cursor-drop-shape');
  let targetX = innerWidth / 2, targetY = innerHeight / 2;
  let currentX = targetX, currentY = targetY, velocityX = 0, velocityY = 0;
  let started = false;
  const updateProgress = () => {
    const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    cursor.style.setProperty('--cursor-progress', `${Math.min(100, Math.max(8, scrollY / max * 100))}%`);
  };
  updateProgress();
  addEventListener('scroll', updateProgress, { passive: true });
  document.addEventListener('mousemove', (e) => {
    targetX = e.clientX; targetY = e.clientY;
    if (!started) {
      currentX = targetX; currentY = targetY; started = true;
    }
    cursor.classList.add('visible');
    const target = e.target.closest('a, button, .gallery-item, input, select, .service-card');
    cursor.classList.toggle('hover-target', !!target);
  });
  const animateDrop = () => {
    velocityX = (velocityX + (targetX - currentX) * .17) * .7;
    velocityY = (velocityY + (targetY - currentY) * .17) * .7;
    currentX += velocityX;
    currentY += velocityY;
    const speed = Math.min(18, Math.hypot(velocityX, velocityY));
    const angle = speed > .15 ? Math.atan2(velocityY, velocityX) * 180 / Math.PI + 90 : 0;
    shape.style.setProperty('--drop-angle', `${angle}deg`);
    shape.style.setProperty('--drop-stretch', String(1 + speed * .018));
    shape.style.setProperty('--drop-squash', String(1 - Math.min(.18, speed * .009)));
    cursor.style.left = `${currentX}px`;
    cursor.style.top = `${currentY}px`;
    requestAnimationFrame(animateDrop);
  };
  requestAnimationFrame(animateDrop);
  document.addEventListener('mousedown', () => cursor.classList.add('pressed'));
  document.addEventListener('mouseup', () => cursor.classList.remove('pressed'));
  document.addEventListener('mouseleave', () => cursor.classList.remove('visible'));
}

// Водяной отклик только по клику: не оставляет постоянный след за курсором
function initSoapTrail() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.addEventListener('click', (e) => {
    const ripple = document.createElement('span');
    ripple.className = 'water-click-ripple';
    ripple.style.left = `${e.clientX}px`;
    ripple.style.top = `${e.clientY}px`;
    document.body.appendChild(ripple);
    setTimeout(() => ripple.remove(), 650);
    for (let index = 0; index < 3; index += 1) {
      const spark = document.createElement('span');
      const angle = (-135 + index * 135 + Math.random() * 24) * Math.PI / 180;
      const distance = 17 + Math.random() * 13;
      spark.className = 'water-click-spark';
      spark.style.left = `${e.clientX}px`;
      spark.style.top = `${e.clientY}px`;
      spark.style.setProperty('--spark-x', `${Math.cos(angle) * distance}px`);
      spark.style.setProperty('--spark-y', `${Math.sin(angle) * distance}px`);
      document.body.appendChild(spark);
      setTimeout(() => spark.remove(), 520);
    }
  });
}

// Магнитные кнопки — притягиваются к курсору в пределах своей области
function initMagneticButtons(selector = '.btn-magnetic') {
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  document.querySelectorAll(selector).forEach(btn => {
    btn.addEventListener('mousemove', (e) => {
      const rect = btn.getBoundingClientRect();
      const relX = e.clientX - rect.left - rect.width / 2;
      const relY = e.clientY - rect.top - rect.height / 2;
      btn.style.transform = `translate(${relX * 0.25}px, ${relY * 0.35}px)`;
    });
    btn.addEventListener('mouseleave', () => { btn.style.transform = 'translate(0,0)'; });
  });
}

// Prefetch страницы при наведении на ссылку (мгновенный переход)
function initPrefetchOnHover(selector) {
  document.querySelectorAll(selector).forEach(link => {
    let done = false;
    link.addEventListener('mouseenter', () => {
      if (done) return;
      done = true;
      const l = document.createElement('link');
      l.rel = 'prefetch'; l.href = link.href;
      document.head.appendChild(l);
    }, { once: true });
  });
}
// suffix — например " ₽"; duration в мс.
function animateCount(el, target, { duration = 900, suffix = '', prefix = '' } = {}) {
  if (!el) return;
  const start = 0;
  const startTime = performance.now();
  function step(now) {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const value = Math.round(start + (target - start) * eased);
    el.textContent = prefix + value.toLocaleString('ru-RU') + suffix;
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Запускает animateCount, как только элемент появляется в зоне видимости (один раз).
function animateCountOnView(el, target, opts = {}) {
  if (!el) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        animateCount(el, target, opts);
        io.unobserve(el);
      }
    });
  }, { threshold: 0.3 });
  io.observe(el);
}

// ---- Reveal со стаггером: элементы с классом .reveal внутри контейнера
// появляются по очереди, а не все разом. Вызывать после того, как DOM готов
// (включая динамически отрисованные сетки — сервисы, галерею и т.п.)
function initRevealObserver(selector = '.reveal') {
  const els = document.querySelectorAll(selector);
  els.forEach((el, i) => {
    if (!el.style.getPropertyValue('--d')) {
      el.style.setProperty('--d', Math.min(i * 0.06, 0.4) + 's');
    }
  });
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });
  els.forEach(el => io.observe(el));
  return io;
}

// ---- Лайтбокс: клик по любой картинке внутри .gallery-item открывает
// полноэкранный просмотр. Работает и с картинками, добавленными позже (делегирование).
function initBeforeAfterSliders() {
  document.querySelectorAll('[data-ba-slider]').forEach((slider) => {
    if (slider.dataset.baReady) return;
    slider.dataset.baReady = '1';
    const before = slider.querySelector('[data-ba-before]');
    const handle = slider.querySelector('[data-ba-handle]');
    let dragging = false;
    function setPercent(clientX) {
      const rect = slider.getBoundingClientRect();
      let pct = ((clientX - rect.left) / rect.width) * 100;
      pct = Math.max(0, Math.min(100, pct));
      before.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
      handle.style.left = pct + '%';
    }
    slider.addEventListener('pointerdown', (e) => {
      dragging = true;
      slider.setPointerCapture(e.pointerId);
      setPercent(e.clientX);
    });
    slider.addEventListener('pointermove', (e) => { if (dragging) setPercent(e.clientX); });
    slider.addEventListener('pointerup', () => { dragging = false; });
    slider.addEventListener('pointercancel', () => { dragging = false; });
  });
}

function initLightbox() {
  if (document.getElementById('lightboxOverlay')) return;
  const overlay = document.createElement('div');
  overlay.className = 'lightbox-overlay';
  overlay.id = 'lightboxOverlay';
  overlay.innerHTML = `
    <button class="lightbox-close" aria-label="Закрыть">✕</button>
    <button class="lightbox-prev" aria-label="Предыдущая фотография">‹</button>
    <img src="" alt="">
    <button class="lightbox-next" aria-label="Следующая фотография">›</button>
    <div class="lightbox-counter"></div>
    <div class="lightbox-caption"></div>
  `;
  document.body.appendChild(overlay);
  const imgEl = overlay.querySelector('img');
  const capEl = overlay.querySelector('.lightbox-caption');
  const counterEl = overlay.querySelector('.lightbox-counter');
  let items = [], currentIndex = 0, touchStartX = 0;

  function close() { overlay.classList.remove('open'); document.body.classList.remove('lightbox-open'); }
  function show(index) {
    if (!items.length) return;
    currentIndex = (index + items.length) % items.length;
    const item = items[currentIndex];
    const img = item.querySelector('img');
    const cap = item.querySelector('.gallery-cap');
    if (!img) return;
    imgEl.src = img.src;
    imgEl.alt = img.alt || '';
    capEl.textContent = cap ? cap.textContent : '';
    counterEl.textContent = `${currentIndex + 1} / ${items.length}`;
  }
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('.lightbox-close').addEventListener('click', close);
  overlay.querySelector('.lightbox-prev').addEventListener('click', () => show(currentIndex - 1));
  overlay.querySelector('.lightbox-next').addEventListener('click', () => show(currentIndex + 1));
  overlay.addEventListener('touchstart', e => { touchStartX = e.changedTouches[0].clientX; }, { passive: true });
  overlay.addEventListener('touchend', e => {
    const distance = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(distance) > 48) show(currentIndex + (distance < 0 ? 1 : -1));
  }, { passive: true });
  document.addEventListener('keydown', (e) => {
    if (!overlay.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    if (e.key === 'ArrowLeft') show(currentIndex - 1);
    if (e.key === 'ArrowRight') show(currentIndex + 1);
  });

  document.addEventListener('click', (e) => {
    const item = e.target.closest('.gallery-item');
    if (!item) return;
    const img = item.querySelector('img');
    if (!img) return;
    items = [...document.querySelectorAll('.gallery-item')].filter(node => node.querySelector('img'));
    show(items.indexOf(item));
    overlay.classList.add('open');
    document.body.classList.add('lightbox-open');
  });
}

// ---- Scroll-spy: подсвечивает активный пункт навигации по текущей секции
function initScrollSpy(navSelector = '.navlinks a', sectionSelector = 'section[id]') {
  const links = document.querySelectorAll(navSelector);
  const sections = document.querySelectorAll(sectionSelector);
  if (!links.length || !sections.length) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + entry.target.id));
      }
    });
  }, { threshold: 0.4, rootMargin: '-80px 0px -60% 0px' });
  sections.forEach(s => io.observe(s));
}

// ---- Курсор-подсветка: следует за мышью внутри контейнера (обычно .hero)
function initCursorGlow(containerSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  const glow = document.createElement('div');
  glow.className = 'cursor-glow';
  container.prepend(glow);
  container.addEventListener('mousemove', (e) => {
    const rect = container.getBoundingClientRect();
    glow.style.setProperty('--x', (e.clientX - rect.left) + 'px');
    glow.style.setProperty('--y', (e.clientY - rect.top) + 'px');
  });
}
