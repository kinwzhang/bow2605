// api.js — fetch() wrapper with CSRF + 401 handling.
//
// Phase 6: real implementation. All public functions throw ApiError on
// non-2xx responses. 401 triggers a redirect to /login.html.

import { csrf, setCsrf } from './state.js';

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
    this.message = message;
  }
}

function handleUnauthenticated() {
  // Replace the current page with the login screen. Using replace() so the
  // back button doesn't bounce back into the app shell.
  window.location.replace('/login.html');
}

async function request(method, path, body) {
  const headers = {
    'Accept': 'application/json',
  };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (csrf && method !== 'GET') headers['X-CSRF-Token'] = csrf;

  const resp = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (resp.status === 401) {
    handleUnauthenticated();
    // Don't throw — the page is already redirecting. Return a never-resolving
    // promise so callers awaiting this don't continue.
    return new Promise(() => {});
  }

  let payload = null;
  try { payload = await resp.json(); } catch (_) { /* empty body or 204 */ }

  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      payload && payload.code,
      (payload && payload.error) || `request failed: ${resp.status}`,
    );
  }
  return payload;
}

export const apiGet = (path) => request('GET', path);
export const apiPost = (path, body) => request('POST', path, body);
export const apiPatch = (path, body) => request('PATCH', path, body);
export const apiPut = (path, body) => request('PUT', path, body);
export const apiDelete = (path) => request('DELETE', path);