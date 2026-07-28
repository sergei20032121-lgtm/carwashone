// ==== НАСТРОЙКА ====
// Адрес backend API. Если открываешь файлы напрямую (file://) или сайт живёт
// на другом домене — поменяй на реальный адрес сервера.
const API_BASE = window.location.origin.startsWith('http')
  ? window.location.origin.replace(/:\d+$/, ':8123')
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
  cursor.innerHTML = '<svg viewBox="0 0 24 24" fill="#BE3B3B"><path d="M12 2c4 5.5 7 9.3 7 13a7 7 0 1 1-14 0c0-3.7 3-7.5 7-13Z"/></svg>';
  document.body.appendChild(cursor);
  let raf = null, x = 0, y = 0;
  document.addEventListener('mousemove', (e) => {
    x = e.clientX; y = e.clientY;
    cursor.classList.add('visible');
    if (!raf) raf = requestAnimationFrame(() => {
      cursor.style.left = x + 'px'; cursor.style.top = y + 'px'; raf = null;
    });
    const target = e.target.closest('a, button, .gallery-item, input, select, .service-card');
    cursor.classList.toggle('hover-target', !!target);
  });
  document.addEventListener('mouseleave', () => cursor.classList.remove('visible'));
}

// Мыльный след из пузырьков за курсором (лёгкий, редкий — не спамит)
function initSoapTrail() {
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  let lastSpawn = 0;
  document.addEventListener('mousemove', (e) => {
    const now = performance.now();
    if (now - lastSpawn < 90) return;
    lastSpawn = now;
    const size = 5 + Math.random() * 7;
    const b = document.createElement('div');
    b.className = 'soap-bubble';
    b.style.width = size + 'px';
    b.style.height = size + 'px';
    b.style.left = (e.clientX + (Math.random() * 10 - 5)) + 'px';
    b.style.top = (e.clientY + (Math.random() * 10 - 5)) + 'px';
    document.body.appendChild(b);
    setTimeout(() => b.remove(), 1200);
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
function initLightbox() {
  if (document.getElementById('lightboxOverlay')) return;
  const overlay = document.createElement('div');
  overlay.className = 'lightbox-overlay';
  overlay.id = 'lightboxOverlay';
  overlay.innerHTML = `
    <button class="lightbox-close" aria-label="Закрыть">✕</button>
    <img src="" alt="">
    <div class="lightbox-caption"></div>
  `;
  document.body.appendChild(overlay);
  const imgEl = overlay.querySelector('img');
  const capEl = overlay.querySelector('.lightbox-caption');

  function close() { overlay.classList.remove('open'); }
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('.lightbox-close').addEventListener('click', close);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  document.addEventListener('click', (e) => {
    const item = e.target.closest('.gallery-item');
    if (!item) return;
    const img = item.querySelector('img');
    if (!img) return;
    const cap = item.querySelector('.gallery-cap');
    imgEl.src = img.src;
    imgEl.alt = img.alt || '';
    capEl.textContent = cap ? cap.textContent : (img.alt || '');
    overlay.classList.add('open');
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
