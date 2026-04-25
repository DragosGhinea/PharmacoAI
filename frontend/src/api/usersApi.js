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

export function listAgents(userId) {
  return apiRequest('/agents', {
    headers: {
      'X-User-Id': userId,
    },
  });
}

export function chatWithAgent(userId, agentId, payload) {
  return apiRequest(`/agents/${agentId}/chat`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify(payload),
  });
}

export function chatWithOrchestrator(userId, payload) {
  return apiRequest('/agents/chat', {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify(payload),
  });
}

export async function chatWithOrchestratorStream(userId, payload, onEvent, options = {}) {
  const response = await fetch(`${API_BASE_URL}/agents/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
    },
    body: JSON.stringify(payload),
    signal: options?.signal,
  });

  if (!response.ok) {
    let message = 'Request failed';
    try {
      const data = await response.json();
      message = formatDetail(data.detail) ?? message;
    } catch {
      // Keep fallback.
    }
    throw new Error(message);
  }

  if (!response.body) {
    throw new Error('Streaming response body is unavailable');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalData = null;

  function handleEventPayload(payloadText) {
    if (!payloadText) {
      return;
    }

    let event;
    try {
      event = JSON.parse(payloadText);
    } catch {
      return;
    }

    if (typeof onEvent === 'function') {
      onEvent(event);
    }

    if (event.type === 'error') {
      const statusInfo = event.status_code ? ` (HTTP ${event.status_code})` : '';
      throw new Error(String(event.message || 'Streaming request failed') + statusInfo);
    }
    if (event.type === 'final') {
      finalData = event.data;
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';

    for (const rawChunk of chunks) {
      const chunk = rawChunk.trim();
      if (!chunk) {
        continue;
      }

      // Support SSE framing: data: {json}
      if (chunk.startsWith('data:')) {
        const payloadText = chunk
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('');
        handleEventPayload(payloadText);
        continue;
      }

      // Backward-compatible plain NDJSON line fallback.
      const lines = chunk.split('\n');
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) {
          continue;
        }
        handleEventPayload(line);
      }
    }
  }

  if (!finalData) {
    throw new Error('No final response received from stream');
  }

  return finalData;
}

export function cancelOrchestratorStream(userId, requestId) {
  return apiRequest('/agents/chat/stream/cancel', {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify({ request_id: requestId }),
  });
}

export function handoffAgents(userId, payload) {
  return apiRequest('/agents/handoff', {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: JSON.stringify(payload),
  });
}

export function getAgentConversation(userId, conversationId) {
  return apiRequest(`/agents/conversations/${conversationId}`, {
    headers: {
      'X-User-Id': userId,
    },
  });
}
