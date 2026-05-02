const PHARMACIST_CHAT_HISTORY_KEY_PREFIX = 'pharmacoai_pharmacist_chat_history_';

export const VISIBLE_ASSISTANT_SENDERS = new Set([
  'pharmacist-general-agent',
  'layman-translator-agent',
  'orchestrator-agent',
]);

export function readPharmacistChatHistory(userId) {
  if (typeof window === 'undefined' || !userId) {
    return [];
  }

  const raw = window.localStorage.getItem(`${PHARMACIST_CHAT_HISTORY_KEY_PREFIX}${userId}`);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((entry) => entry && typeof entry === 'object' && entry.conversationId)
      .map((entry) => ({
        conversationId: String(entry.conversationId),
        title: String(entry.title || 'Untitled conversation'),
        updatedAt: String(entry.updatedAt || new Date().toISOString()),
        lastAgent: String(entry.lastAgent || ''),
      }))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  } catch {
    return [];
  }
}

export function persistPharmacistChatHistory(userId, history) {
  if (typeof window === 'undefined' || !userId) {
    return;
  }
  window.localStorage.setItem(`${PHARMACIST_CHAT_HISTORY_KEY_PREFIX}${userId}`, JSON.stringify(history));
}

export function upsertConversationHistoryEntry(history, nextEntry) {
  const filtered = history.filter((entry) => entry.conversationId !== nextEntry.conversationId);
  const merged = [nextEntry, ...filtered];
  return merged.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function shouldDisplayAssistantMessage(item, idx, arr) {
  if (item?.role !== 'assistant') {
    return true;
  }
  const sender = String(item?.sender || '').trim();
  if (!sender) {
    return idx === arr.length - 1;
  }
  return VISIBLE_ASSISTANT_SENDERS.has(sender);
}

export function hasVisibleTimelineMessages(conversationMessages) {
  return conversationMessages.some((item, idx, arr) => shouldDisplayAssistantMessage(item, idx, arr));
}
