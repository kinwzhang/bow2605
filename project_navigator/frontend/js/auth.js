// auth.js — login / register / logout / me, plus session bootstrap.
//
// Public surface:
//   bootstrap() — call on app load. Redirects to /login.html if unauthenticated.
//   login(username, password)
//   register(username, password)
//   logout()
//   switchUser() — alias for logout(); the user picker UI in the header
//                  will use this in Phase 7.
//
// All four mutations hit the real /api/auth/* endpoints defined in
// backend/app.py. The CSRF token returned in each response is stored in
// state.csrf so api.js can attach it to subsequent mutating requests.

import { setCsrf, setCurrentUser, setActiveProjectId } from './state.js';

const ME_PATH = '/api/auth/me';
const LOGIN_PATH = '/api/auth/login';
const REGISTER_PATH = '/api/auth/register';
const LOGOUT_PATH = '/api/auth/logout';

class AuthError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function jsonRequest(method, path, body) {
  const resp = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let payload = null;
  try { payload = await resp.json(); } catch (_) { /* empty body */ }
  if (!resp.ok) {
    throw new AuthError(
      resp.status,
      payload && payload.code,
      (payload && payload.error) || `request failed: ${resp.status}`,
    );
  }
  return payload || {};
}

export async function login(username, password) {
  const body = await jsonRequest('POST', LOGIN_PATH, { username, password });
  setCsrf(body.csrf_token);
  setCurrentUser(body.user);
  return body;
}

export async function register(username, password) {
  const body = await jsonRequest('POST', REGISTER_PATH, { username, password });
  setCsrf(body.csrf_token);
  setCurrentUser(body.user);
  return body;
}

export async function logout(csrfToken) {
  await jsonRequest('POST', LOGOUT_PATH, {});
  // csrfToken is required by the backend; in practice we always pass it.
  // We don't clear csrf here — the next /me call will issue a fresh one
  // for the next user (or fail with 401 if no user is logged in).
  return csrfToken;
}

export async function bootstrap({ redirectIfUnauth = true } = {}) {
  try {
    const body = await jsonRequest('GET', ME_PATH);
    setCsrf(body.csrf_token);
    setCurrentUser(body.user);
    setActiveProjectId(body.active_project_id);
    return body;
  } catch (err) {
    if (err.status === 401 && redirectIfUnauth) {
      window.location.replace('/login.html');
      return null;
    }
    throw err;
  }
}

// Wire up the login form when this module loads (only on login.html).
const form = document.getElementById('auth-form');
if (form) {
  const submitBtn = document.getElementById('submit-btn');
  const errEl = document.getElementById('error-msg');
  const tagline = document.getElementById('mode-tagline');
  const toggleBtn = document.getElementById('toggle-mode');
  const toggleText = document.getElementById('toggle-text');

  let mode = 'login'; // or 'register'

  function applyMode() {
    if (mode === 'register') {
      submitBtn.textContent = 'Create account';
      tagline.textContent = 'Create a new account.';
      toggleText.textContent = 'Already have an account?';
      toggleBtn.textContent = 'Sign in instead';
      toggleBtn.dataset.mode = 'login';
    } else {
      submitBtn.textContent = 'Sign in';
      tagline.textContent = 'Sign in to your account.';
      toggleText.textContent = 'New here?';
      toggleBtn.textContent = 'Create an account';
      toggleBtn.dataset.mode = 'register';
    }
    errEl.hidden = true;
  }

  toggleBtn.addEventListener('click', () => {
    mode = toggleBtn.dataset.mode === 'register' ? 'register' : 'login';
    applyMode();
  });

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    errEl.hidden = true;
    submitBtn.disabled = true;
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    try {
      if (mode === 'register') {
        await register(username, password);
      } else {
        await login(username, password);
      }
      // Success → go to the app. If the user has no active project yet, the
      // app shell will show the empty state.
      window.location.replace('/');
    } catch (err) {
      errEl.textContent = err.message || 'Sign-in failed.';
      errEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });

  applyMode();
}