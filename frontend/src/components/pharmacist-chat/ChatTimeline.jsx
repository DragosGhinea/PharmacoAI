import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import McpTurnCard from './McpTurnCard';
import { hasVisibleTimelineMessages, shouldDisplayAssistantMessage, VISIBLE_ASSISTANT_SENDERS } from '../../utils/pharmacistChatUtils';

const AGENT_WORK_SENDERS = new Set([
  ...VISIBLE_ASSISTANT_SENDERS,
  'medication-normalization-agent',
  'medication-evidence-gathering-agent',
  'medication-info-agent',
  'safety-contraindication-agent',
]);

function roleBadgeClass(role) {
  if (role === 'user') {
    return 'bg-secondary text-white';
  }
  if (role === 'assistant') {
    return 'bg-primary-container text-white';
  }
  return 'bg-surface-container-high text-on-surface-variant';
}

function roleLabel(message) {
  if (message.role === 'user') {
    return 'You';
  }
  if (message.sender) {
    return message.sender;
  }
  return message.role;
}

function normalizeMarkdownContent(value) {
  if (typeof value !== 'string') {
    return '';
  }

  let normalized = value.replace(/\r\n/g, '\n');
  if (normalized.includes('\\n')) {
    normalized = normalized.replace(/\\n/g, '\n');
  }
  return normalized;
}

function normalizeFingerprintText(value) {
  return normalizeMarkdownContent(value || '').trim().replace(/\s+/g, ' ');
}

function turnPreviewText(turn) {
  const preview = String(turn?.response || turn?.stage_output || '').trim();
  return preview;
}

function normalizeMessageRole(message) {
  if (!message || typeof message !== 'object') {
    return message;
  }
  const sender = String(message.sender || '').trim();
  if (message.role !== 'user' && sender && AGENT_WORK_SENDERS.has(sender)) {
    return { ...message, role: 'assistant' };
  }
  return message;
}

function shouldIncludeInAgentWork(message) {
  if (!message || typeof message !== 'object') {
    return false;
  }
  if (message.role !== 'assistant') {
    return false;
  }
  const sender = String(message.sender || '').trim();
  return Boolean(sender && AGENT_WORK_SENDERS.has(sender));
}

function truncateMessage(value, limit) {
  if (typeof value !== 'string') {
    return '';
  }
  const trimmed = value.trim();
  if (trimmed.length <= limit) {
    return trimmed;
  }
  return `${trimmed.slice(0, limit).trimEnd()}...`;
}

function MarkdownMessage({ content }) {
  return (
    <div className="max-w-none text-on-surface-variant text-sm leading-relaxed space-y-3 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-3 whitespace-pre-wrap leading-relaxed">{children}</p>,
          ul: ({ children }) => <ul className="my-3 list-disc pl-5 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="my-3 list-decimal pl-5 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => <blockquote className="my-3 border-l-4 border-outline-variant/60 pl-3 italic">{children}</blockquote>,
          code: ({ inline, children }) =>
            inline ? (
              <code className="rounded bg-surface-container-low px-1 py-0.5 text-xs">{children}</code>
            ) : (
              <code className="block rounded-lg bg-surface-container-low p-3 text-xs whitespace-pre-wrap leading-relaxed">{children}</code>
            ),
          pre: ({ children }) => <pre className="my-3 overflow-x-auto">{children}</pre>,
        }}
      >
        {normalizeMarkdownContent(content || '')}
      </ReactMarkdown>
    </div>
  );
}

function AgentWorkBox({ children, compactMode }) {
  const [isExpanded, setIsExpanded] = useState(true);
  return (
    <div className="mr-auto w-full max-w-[92%]">
      <button
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
        className="w-full text-left"
      >
        <div className={`flex items-center gap-3 ${compactMode ? 'py-1' : 'py-2'}`}>
          <div className="h-px flex-1 bg-outline-variant/60" />
          <div className="flex items-center gap-2">
            <span className="px-2 py-1 rounded-full text-xs font-semibold bg-secondary text-white">Agent Work</span>
            <span className="text-xs text-on-surface-variant">{isExpanded ? 'Click to collapse' : 'Click to expand'}</span>
          </div>
          <div className="h-px flex-1 bg-outline-variant/60" />
        </div>
      </button>

      {isExpanded && (
        <>
          <div className={`mt-2 space-y-3 ${compactMode ? '' : 'pl-1'}`}>{children}</div>
          <div className={`mt-3 flex items-center gap-3 ${compactMode ? 'py-1' : 'py-2'}`}>
            <div className="h-px flex-1 bg-outline-variant/60" />
            <button
              type="button"
              onClick={() => setIsExpanded(false)}
              className="px-2 py-1 rounded-full text-xs font-semibold border border-outline-variant/60 text-on-surface-variant"
            >
              Collapse Agent Work above
            </button>
            <div className="h-px flex-1 bg-outline-variant/60" />
          </div>
        </>
      )}
    </div>
  );
}

export default function ChatTimeline({
  conversationMessages,
  chatTurns,
  agentWorkHistory = [],
  assistantBaseIndex = 0,
  hasLiveTrace,
  isSending,
  compactMode = false,
}) {
  const hasVisibleMessages = hasVisibleTimelineMessages(conversationMessages);
  const agentWorkAssistantFingerprints = new Set();
  (Array.isArray(agentWorkHistory) ? agentWorkHistory : []).forEach((entry) => {
    const assistantItems = Array.isArray(entry?.assistantMessages) ? entry.assistantMessages : [];
    assistantItems.forEach((message) => {
      const sender = String(message?.sender || 'assistant');
      const content = normalizeFingerprintText(message?.content || '');
      if (content) {
        agentWorkAssistantFingerprints.add(`${sender}|${content}`);
      }
    });
  });

  function renderMessageBubble(message, key) {
    const content = compactMode ? truncateMessage(String(message.content || ''), 280) : message.content;
    return (
      <div
        key={key}
        className={
          message.role === 'user'
            ? `ml-auto max-w-[85%] rounded-2xl border border-secondary/40 bg-secondary/10 ${compactMode ? 'p-3' : 'p-4'}`
            : `mr-auto max-w-[90%] rounded-2xl border border-outline-variant/40 bg-surface ${compactMode ? 'p-3' : 'p-4'}`
        }
      >
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-1 rounded-md text-xs font-semibold ${roleBadgeClass(message.role)}`}>
            {roleLabel(message)}
          </span>
          {message.timestamp && (
            <span className="text-[11px] text-on-surface-variant">{new Date(message.timestamp).toLocaleTimeString()}</span>
          )}
        </div>
        <MarkdownMessage content={content} />
      </div>
    );
  }

  function renderLiveTurnDraft(turn, keyPrefix = 'live') {
    const rawDraft = turnPreviewText(turn);
    const draft = compactMode ? truncateMessage(rawDraft, 240) : rawDraft;
    if (!draft) {
      return null;
    }
    return (
      <div
        key={`${keyPrefix}-draft-${turn.agent_id || 'agent'}`}
        className={`mr-auto max-w-[90%] rounded-2xl border border-outline-variant/40 bg-surface ${compactMode ? 'p-3' : 'p-4'}`}
      >
        <div className="flex items-center gap-2 mb-2">
          <span className="px-2 py-1 rounded-md text-xs font-semibold bg-primary-container text-white">
            {String(turn?.agent_id || 'agent')} (Draft)
          </span>
        </div>
        <MarkdownMessage content={draft} />
      </div>
    );
  }

  return (
    <div className="mt-2 flex-1 space-y-3 overflow-y-auto min-h-0">
      {!hasVisibleMessages && !hasLiveTrace && !isSending ? (
        <div className="rounded-2xl border border-outline-variant/50 bg-surface p-4 text-sm text-on-surface-variant">
          No chat turns yet. Send a message to start a tracked conversation.
        </div>
      ) : (
        (() => {
          if (isSending && chatTurns.length > 0) {
            const liveTimeline = [];
            const seenDrafts = new Set();
            const existingDrafts = new Set();

            conversationMessages.forEach((message, index, arr) => {
              const normalizedMessage = normalizeMessageRole(message);
              if (!shouldDisplayAssistantMessage(normalizedMessage, index, arr)) {
                return;
              }
              if (normalizedMessage.role === 'assistant') {
                const sender = String(normalizedMessage.sender || 'assistant');
                const content = normalizeFingerprintText(normalizedMessage.content || '');
                if (content) {
                  if (agentWorkAssistantFingerprints.has(`${sender}|${content}`)) {
                    return;
                  }
                  existingDrafts.add(`${sender}|${content}`);
                }
              }
              liveTimeline.push(renderMessageBubble(normalizedMessage, `${message.timestamp || index}-${index}`));
            });

            chatTurns.forEach((turn, turnIndex) => {
              liveTimeline.push(<McpTurnCard key={`live-turn-${turnIndex}`} turn={turn} turnIndex={turnIndex} />);
              const draft = turnPreviewText(turn);
              const draftFingerprint = `${turn.agent_id || 'agent'}|${normalizeFingerprintText(draft)}`;
              if (!draft || seenDrafts.has(draftFingerprint) || existingDrafts.has(draftFingerprint)) {
                return;
              }
              seenDrafts.add(draftFingerprint);
              const draftNode = renderLiveTurnDraft(turn, `live-${turnIndex}`);
              if (draftNode) {
                liveTimeline.push(draftNode);
              }
            });

            return liveTimeline;
          }

          const timeline = [];
          const agentWorkEntries = Array.isArray(agentWorkHistory)
            ? agentWorkHistory
            : [];
          let assistantTurnIndex = 0;
          let assistantSeenCount = 0;
          let lastAssistantFingerprint = '';
          let lastAssistantIndex = -1;

          const normalizedMessages = conversationMessages.map((message) => normalizeMessageRole(message));
          let assistantCounter = 0;
          normalizedMessages.forEach((message, index, arr) => {
            if (message.role === 'assistant') {
              const isVisible = shouldDisplayAssistantMessage(message, index, arr);
              if (isVisible && assistantCounter >= assistantBaseIndex) {
                lastAssistantIndex = index;
              }
              assistantCounter += 1;
            }
          });

          const assistantIndexMap = [];
          normalizedMessages.forEach((message, index, arr) => {
            if (message.role !== 'assistant') {
              return;
            }
            if (!shouldDisplayAssistantMessage(message, index, arr)) {
              return;
            }
            assistantIndexMap.push(index);
          });

          const agentWorkBlocks = new Map();
          agentWorkEntries.forEach((entry, idx) => {
            if (!entry || !Array.isArray(entry.turns) || entry.turns.length === 0) {
              return;
            }
            const startIndex = Number(entry.assistantBaseIndex || 0);
            const endIndex = Math.max(startIndex + entry.turns.length - 1, 0);
            const messageIndex = assistantIndexMap[endIndex];
            if (typeof messageIndex !== 'number') {
              return;
            }
            const items = [];
            const turnCards = entry.turns.map((turn, turnIndex) => (
              <McpTurnCard key={`hist-turn-${idx}-${turnIndex}`} turn={turn} turnIndex={turnIndex} />
            ));
            items.push(...turnCards);
            const assistantItems = Array.isArray(entry.assistantMessages) ? entry.assistantMessages : [];
            assistantItems.forEach((message, msgIndex) => {
              items.push(
                renderMessageBubble(
                  normalizeMessageRole(message),
                  `hist-msg-${idx}-${msgIndex}-${message.timestamp || msgIndex}`
                )
              );
            });
            agentWorkBlocks.set(messageIndex, (
              <AgentWorkBox key={`agent-work-${idx}`} compactMode={compactMode}>
                {items}
              </AgentWorkBox>
            ));
          });

          function pushDraftTurnMessage(turn, suffix = 'Draft') {
            const rawDraft = turnPreviewText(turn);
            if (!rawDraft) {
              return;
            }
            const sender = String(turn?.agent_id || 'agent');
            const fingerprint = `${sender}|${normalizeFingerprintText(rawDraft)}`;
            if (fingerprint === lastAssistantFingerprint) {
              return;
            }
            lastAssistantFingerprint = fingerprint;
            const displayDraft = compactMode ? truncateMessage(rawDraft, 240) : rawDraft;

            timeline.push(
              <div
                key={`draft-${sender}-${fingerprint}`}
                className={`mr-auto max-w-[90%] rounded-2xl border border-outline-variant/40 bg-surface ${compactMode ? 'p-3' : 'p-4'}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-1 rounded-md text-xs font-semibold bg-primary-container text-white">
                    {sender} ({suffix})
                  </span>
                </div>
                <MarkdownMessage content={displayDraft} />
              </div>
            );
          }

          normalizedMessages.forEach((normalizedMessage, index, arr) => {
            let matchedTurn = null;
            if (normalizedMessage.role === 'assistant') {
              if (assistantSeenCount >= assistantBaseIndex && assistantTurnIndex < chatTurns.length) {
                matchedTurn = chatTurns[assistantTurnIndex];
                assistantTurnIndex += 1;
              }
              assistantSeenCount += 1;
            }

            const isVisibleAssistant = shouldDisplayAssistantMessage(normalizedMessage, index, arr);
            if (normalizedMessage.role === 'assistant' && assistantSeenCount <= assistantBaseIndex) {
              if (isVisibleAssistant) {
                timeline.push(renderMessageBubble(normalizedMessage, `${normalizedMessage.timestamp || index}-${index}`));
              }
              return;
            }
            if (!isVisibleAssistant && shouldIncludeInAgentWork(normalizedMessage)) {
              const sender = String(normalizedMessage.sender || 'assistant');
              const content = normalizeFingerprintText(normalizedMessage.content || '');
              const fingerprint = `${sender}|${content}`;
              if (content && fingerprint !== lastAssistantFingerprint) {
                lastAssistantFingerprint = fingerprint;
                agentWorkItems.push(
                  renderMessageBubble(normalizedMessage, `${normalizedMessage.timestamp || index}-${index}`)
                );
              }
            }

            if (!isVisibleAssistant) {
              if (isSending && matchedTurn) {
                pushDraftTurnMessage(matchedTurn);
              }
              return;
            }

            if (normalizedMessage.role === 'assistant') {
              const sender = String(normalizedMessage.sender || 'assistant');
              const content = normalizeFingerprintText(normalizedMessage.content || '');
              const fingerprint = `${sender}|${content}`;
              if (!content || fingerprint === lastAssistantFingerprint) {
                return;
              }
              lastAssistantFingerprint = fingerprint;
              if (agentWorkAssistantFingerprints.has(fingerprint)) {
                return;
              }
              const bubble = renderMessageBubble(normalizedMessage, `${normalizedMessage.timestamp || index}-${index}`);
              const agentWorkBlock = agentWorkBlocks.get(index);
              if (agentWorkBlock) {
                timeline.push(agentWorkBlock);
              }
              timeline.push(bubble);
              return;
            }

            timeline.push(renderMessageBubble(normalizedMessage, `${normalizedMessage.timestamp || index}-${index}`));
          });

          while (assistantTurnIndex < chatTurns.length) {
            const tailTurn = chatTurns[assistantTurnIndex];
            if (isSending) {
              pushDraftTurnMessage(tailTurn);
            }
            assistantTurnIndex += 1;
          }

          return timeline;
        })()
      )}

      {isSending && (
        <div className="mr-auto w-full max-w-[92%] rounded-2xl border border-secondary/40 bg-secondary/5 p-4">
          <div className="flex items-center gap-2 text-sm text-on-surface-variant">
            <span className="inline-block h-4 w-4 rounded-full border-2 border-secondary/30 border-t-secondary animate-spin" />
            <span>Running tools and composing answer...</span>
          </div>
        </div>
      )}
    </div>
  );
}
