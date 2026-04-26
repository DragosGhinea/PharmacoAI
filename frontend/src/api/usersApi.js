const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

function formatDetail(detail) {
  if (!detail) {
    return null;
  }

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object' && 'msg' in item) {
          return String(item.msg);
        }
        return null;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join('; ');
    }

    return null;
  }

  if (typeof detail === 'object') {
    if ('msg' in detail && typeof detail.msg === 'string') {
      return detail.msg;
    }
    return JSON.stringify(detail);
  }

  return String(detail);
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = 'Request failed';
    try {
      const payload = await response.json();
      message = formatDetail(payload.detail) ?? message;
    } catch {
      // Keep generic fallback if backend response is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export function listUsers(adminId) {
  return apiRequest('/users', {
    headers: {
      'X-User-Id': adminId,
    },
  });
}

export function createUser(adminId, payload) {
  return apiRequest('/users', {
    method: 'POST',
    headers: {
      'X-User-Id': adminId,
    },
    body: JSON.stringify(payload),
  });
}

export function updateUser(adminId, userId, payload) {
  return apiRequest(`/users/${userId}`, {
    method: 'PUT',
    headers: {
      'X-User-Id': adminId,
    },
    body: JSON.stringify(payload),
  });
}

export function deleteUser(adminId, userId) {
  return apiRequest(`/users/${userId}`, {
    method: 'DELETE',
    headers: {
      'X-User-Id': adminId,
    },
  });
}

export function listTiers() {
  return apiRequest('/tiers');
}

export function loginUser(email, password) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function getMyUser(userId) {
  return apiRequest('/users/me', {
    headers: {
      'X-User-Id': userId,
    },
  });
}

export function changeMyPassword(userId, currentPassword, newPassword) {
  return apiRequest('/users/me/password', {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export function sendUserMessage(userId, prompt) {
  return apiRequest(`/users/${userId}/messages`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify({ prompt }),
  });
}

export function createSubscriptionCheckout(userId, payload) {
  return apiRequest('/subscriptions/checkout', {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify(payload),
  });
}

export function confirmSubscription(sessionId) {
  return apiRequest('/subscriptions/confirm', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}
