const ADMIN_SESSION_KEY = 'pharmacoai_admin_session';
const PHARMACIST_SESSION_KEY = 'pharmacoai_pharmacist_session';

export function readAdminSession() {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(ADMIN_SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed?.userId && parsed?.username) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function persistAdminSession(session) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
}

export function clearAdminSession() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(ADMIN_SESSION_KEY);
}

export function readPharmacistSession() {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(PHARMACIST_SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed?.userId && parsed?.email) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function persistPharmacistSession(session) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(PHARMACIST_SESSION_KEY, JSON.stringify(session));
}

export function clearPharmacistSession() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(PHARMACIST_SESSION_KEY);
}
