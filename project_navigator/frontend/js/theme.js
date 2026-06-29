// theme.js — theme manager: 3 color themes × light/dark.
//
// Public surface:
//   init() — load saved theme + mode, apply to <html>, wire toggle
//   apply(theme, mode) — set theme + mode, persist, update UI
//   currentTheme — "blue" | "pink" | "yellow"
//   currentMode  — "light" | "dark"

const THEMES = ['blue', 'pink', 'yellow'];
const MODES = ['light', 'dark'];

const THEME_KEY = 'pnav_theme';
const MODE_KEY = 'pnav_mode';

export let currentTheme = 'blue';
export let currentMode = 'light';

function persist(theme, mode) {
  try {
    localStorage.setItem(THEME_KEY, theme);
    localStorage.setItem(MODE_KEY, mode);
  } catch (_) {}
}

function load() {
  let theme = 'blue';
  let mode = 'light';
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t && THEMES.includes(t)) theme = t;
    const m = localStorage.getItem(MODE_KEY);
    if (m && MODES.includes(m)) mode = m;
  } catch (_) {}
  return { theme, mode };
}

export function apply(theme, mode) {
  currentTheme = theme;
  currentMode = mode;
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-mode', mode);
  persist(theme, mode);
  // Dispatch a custom event so other modules can react.
  window.dispatchEvent(new CustomEvent('themechange', { detail: { theme, mode } }));
}

function toggleMode() {
  const next = currentMode === 'light' ? 'dark' : 'light';
  apply(currentTheme, next);
}

export function init() {
  const saved = load();
  apply(saved.theme, saved.mode);
}

export function applyServer(theme, mode) {
  if (THEMES.includes(theme) && MODES.includes(mode)) {
    apply(theme, mode);
  }
}
