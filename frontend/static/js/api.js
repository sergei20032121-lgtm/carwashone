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

// Плавный счётчик чисел — используется для цен и статистики при появлении в вьюпорте.
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
