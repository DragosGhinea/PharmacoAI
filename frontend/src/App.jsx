import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

import { changeMyPassword, chatWithOrchestratorStream, getAgentConversation, getMyUser, loginUser } from './api/usersApi';
import AdminUsersPanel from './components/AdminUsersPanel';

const ADMIN_SESSION_KEY = 'pharmacoai_admin_session';
const PHARMACIST_SESSION_KEY = 'pharmacoai_pharmacist_session';
const PHARMACIST_CHAT_HISTORY_KEY_PREFIX = 'pharmacoai_pharmacist_chat_history_';
const ADMIN_LOGIN_EMAIL = 'admin@pharmacoai.local';

function readPharmacistChatHistory(userId) {
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

function persistPharmacistChatHistory(userId, history) {
  if (typeof window === 'undefined' || !userId) {
    return;
  }
  window.localStorage.setItem(`${PHARMACIST_CHAT_HISTORY_KEY_PREFIX}${userId}`, JSON.stringify(history));
}

function upsertConversationHistoryEntry(history, nextEntry) {
  const filtered = history.filter((entry) => entry.conversationId !== nextEntry.conversationId);
  const merged = [nextEntry, ...filtered];
  return merged.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function readAdminSession() {
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

function persistAdminSession(session) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
}

function clearAdminSession() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(ADMIN_SESSION_KEY);
}

function readPharmacistSession() {
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

function persistPharmacistSession(session) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(PHARMACIST_SESSION_KEY, JSON.stringify(session));
}

function clearPharmacistSession() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(PHARMACIST_SESSION_KEY);
}

function navLinkClass(isActive) {
  if (isActive) {
    return 'text-teal-700 dark:text-teal-400 border-b-2 border-teal-700 dark:border-teal-400 pb-1 manrope text-sm font-semibold';
  }
  return 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors manrope text-sm font-semibold';
}

function TopNav({ currentRoute, isAdminAuthenticated, isPharmacistAuthenticated, onAdminLogout }) {
  const isLandingRoute = currentRoute === 'landing';
  const isAdminRoute = currentRoute === 'admin';
  const isPharmacistRoute = currentRoute === 'pharmacist';

  return (
    <nav className="bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md shadow-sm dark:shadow-none docked full-width top-0 sticky z-50">
      <div className="flex justify-between items-center w-full px-8 py-4 max-w-7xl mx-auto">
        <a className="text-2xl font-bold font-serif text-slate-900 dark:text-slate-50" href="/">
          PharmacoAI
        </a>

        <div className="hidden md:flex gap-8 items-center">
          <a className={navLinkClass(isLandingRoute)} href="/">
            Landing
          </a>
          <a className={navLinkClass(isAdminRoute)} href="/admin">
            Admin
          </a>
          <a className={navLinkClass(isPharmacistRoute)} href="/pharmacist">
            Pharmacist
          </a>
        </div>

        {isAdminRoute && isAdminAuthenticated ? (
          <button
            className="bg-surface-container-low text-primary px-6 py-2.5 rounded-lg font-semibold manrope text-sm hover:bg-surface-container-high transition-colors"
            type="button"
            onClick={onAdminLogout}
          >
            Log Out
          </button>
        ) : isPharmacistRoute && isPharmacistAuthenticated ? (
          <div className="flex items-center gap-2">
            <a
              className="bg-primary-container text-white px-4 py-2.5 rounded-lg font-semibold manrope text-sm hover:scale-95 transition-transform duration-150 active:scale-90"
              href="/pharmacist/chat"
            >
              Agent Chat
            </a>
            <a
              className="bg-surface-container-low text-primary px-4 py-2.5 rounded-lg font-semibold manrope text-sm hover:bg-surface-container-high transition-colors"
              href="/pharmacist/account"
            >
              Account
            </a>
          </div>
        ) : (
          <a
            className="bg-primary-container text-white px-6 py-2.5 rounded-lg font-semibold manrope text-sm hover:scale-95 transition-transform duration-150 active:scale-90"
            href="/pharmacist"
          >
            Pharmacist Login
          </a>
        )}
      </div>
    </nav>
  );
}

function AdminLoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');

    try {
      await onLogin({ username: username.trim(), password });
    } catch (loginError) {
      if (loginError instanceof Error) {
        setError(loginError.message);
      } else {
        setError('Login failed');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-xl mx-auto bg-surface-container-lowest rounded-3xl p-10 border border-outline-variant/40 shadow-sm">
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Admin Access</p>
          <h2 className="text-4xl text-primary font-bold mb-4">Sign In</h2>
          <p className="text-sm text-on-surface-variant mb-8">
            Please log in with your admin credentials to access user management.
          </p>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Username</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Password</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>

            {error && <p className="text-sm font-semibold text-error">{error}</p>}

            <button
              className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Signing In...' : 'Log In'}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function PharmacistLoginPage({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');

    try {
      await onLogin({ email: email.trim(), password });
    } catch (loginError) {
      if (loginError instanceof Error) {
        setError(loginError.message);
      } else {
        setError('Login failed');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-xl mx-auto bg-surface-container-lowest rounded-3xl p-10 border border-outline-variant/40 shadow-sm">
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Pharmacist Access</p>
          <h2 className="text-4xl text-primary font-bold mb-4">Sign In</h2>
          <p className="text-sm text-on-surface-variant mb-8">
            Use your pharmacist account credentials provided by the admin.
          </p>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Email</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="username"
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Password</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>

            {error && <p className="text-sm font-semibold text-error">{error}</p>}

            <button
              className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Signing In...' : 'Log In'}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function PharmacistChatPage({ pharmacistSession }) {
  const [question, setQuestion] = useState('');
  const [userProfile, setUserProfile] = useState(null);
  const [error, setError] = useState('');
  const [messageInfo, setMessageInfo] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [lastFailedRequest, setLastFailedRequest] = useState(null);
  const [conversationId, setConversationId] = useState('');
  const [chatTurns, setChatTurns] = useState([]);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [conversationHistory, setConversationHistory] = useState(() => readPharmacistChatHistory(pharmacistSession.userId));

  useEffect(() => {
    persistPharmacistChatHistory(pharmacistSession.userId, conversationHistory);
  }, [pharmacistSession.userId, conversationHistory]);

  function appendStreamedToolCall(event) {
    const turnIndex = Number(event?.turn_index);
    const call = event?.call;
    const agentId = String(event?.agent_id || 'medication-info-agent');
    if (!Number.isInteger(turnIndex) || !call || typeof call !== 'object') {
      return;
    }

    setChatTurns((current) => {
      const next = [...current];
      while (next.length <= turnIndex) {
        next.push({
          agent_id: agentId,
          provider: 'gemini',
          model: 'streaming',
          thought_summary: 'Running MCP tools...',
          step_status: 'running',
          mcp_tool_calls: [],
          response: '',
          clinician_summary: '',
          patient_summary: '',
          evidence_snippets: [],
          source_links: [],
        });
      }

      const existingTurn = next[turnIndex] || {};
      const existingCalls = Array.isArray(existingTurn.mcp_tool_calls) ? existingTurn.mcp_tool_calls : [];
      next[turnIndex] = {
        ...existingTurn,
        agent_id: existingTurn.agent_id || agentId,
        step_status: existingTurn.step_status || 'running',
        mcp_tool_calls: [...existingCalls, call],
      };
      return next;
    });
  }

  function upsertStreamedStep(event, status) {
    const turnIndex = Number(event?.turn_index);
    const agentId = String(event?.agent_id || 'orchestrator-agent');
    const message = String(event?.message || '');
    const stageInput = typeof event?.stage_input === 'string' ? event.stage_input : '';
    const stageOutput = typeof event?.stage_output === 'string' ? event.stage_output : '';
    const nextStageInput = typeof event?.next_stage_input === 'string' ? event.next_stage_input : '';
    if (!Number.isInteger(turnIndex)) {
      return;
    }

    setChatTurns((current) => {
      const next = [...current];
      while (next.length <= turnIndex) {
        next.push({
          agent_id: agentId,
          provider: 'gemini',
          model: 'streaming',
          thought_summary: message || 'Pipeline stage update',
          step_status: status,
          received_input: stageInput,
          stage_output: stageOutput,
          next_stage_input: nextStageInput,
          mcp_tool_calls: [],
          response: '',
          clinician_summary: '',
          patient_summary: '',
          evidence_snippets: [],
          source_links: [],
        });
      }

      const existingTurn = next[turnIndex] || {};
      next[turnIndex] = {
        ...existingTurn,
        agent_id: existingTurn.agent_id || agentId,
        thought_summary: message || existingTurn.thought_summary || 'Pipeline stage update',
        step_status: status,
        received_input: stageInput || existingTurn.received_input || '',
        stage_output: stageOutput || existingTurn.stage_output || '',
        next_stage_input: nextStageInput || existingTurn.next_stage_input || '',
      };
      return next;
    });
  }

  useEffect(() => {
    let mounted = true;
    async function loadProfile() {
      try {
        const profile = await getMyUser(pharmacistSession.userId);
        if (mounted) {
          setUserProfile(profile);
        }
      } catch (profileError) {
        if (mounted) {
          if (profileError instanceof Error) {
            setError(profileError.message);
          } else {
            setError('Could not load profile');
          }
        }
      }
    }

    loadProfile();
    return () => {
      mounted = false;
    };
  }, [pharmacistSession.userId]);

  async function runAgentRequest({ promptText, conversationIdOverride, optimisticUserMessage, resumePartial }) {
    const trimmedQuestion = String(promptText || '').trim();
    if (!trimmedQuestion) {
      return;
    }

    const targetConversationId = typeof conversationIdOverride === 'string' ? conversationIdOverride : conversationId;

    setError('');
    setMessageInfo('');
    setChatTurns([]);

    if (optimisticUserMessage) {
      setConversationMessages((current) => [
        ...current,
        {
          role: 'user',
          sender: 'user',
          content: trimmedQuestion,
          timestamp: new Date().toISOString(),
        },
      ]);
      setQuestion('');
    }

    const failedRequestContext = {
      message: trimmedQuestion,
      conversationId: targetConversationId || '',
    };

    setIsSending(true);
    try {
      const response = await chatWithOrchestratorStream(
        pharmacistSession.userId,
        {
          message: trimmedQuestion,
          conversation_id: targetConversationId || undefined,
          metadata: resumePartial ? { resume_partial: true } : {},
        },
        (event) => {
          if (event?.type === 'tool_call') {
            appendStreamedToolCall(event);
            return;
          }
          if (event?.type === 'step_started') {
            upsertStreamedStep(event, 'running');
            return;
          }
          if (event?.type === 'step_completed') {
            upsertStreamedStep(event, 'completed');
          }
        }
      );

      const resolvedConversationId = response.conversation_id || targetConversationId || '';
      setConversationId(resolvedConversationId);
      setChatTurns(response.turns || []);
      setMessageInfo(`Conversation ID: ${response.conversation_id}`);
      const turnList = response.turns || [];
      const lastTurn = turnList[turnList.length - 1];
      if (response.conversation_id) {
        setConversationHistory((current) =>
          upsertConversationHistoryEntry(current, {
            conversationId: response.conversation_id,
            title: trimmedQuestion.slice(0, 80) || 'Untitled conversation',
            updatedAt: new Date().toISOString(),
            lastAgent: String(lastTurn?.agent_id || 'orchestrator-agent'),
          })
        );
      }

      if (resolvedConversationId) {
        const conversationResponse = await getAgentConversation(pharmacistSession.userId, resolvedConversationId);
        setConversationMessages(conversationResponse.messages || []);
      }

      const refreshedProfile = await getMyUser(pharmacistSession.userId);
      setUserProfile(refreshedProfile);
      setLastFailedRequest(null);
    } catch (sendError) {
      setLastFailedRequest(failedRequestContext);
      if (sendError instanceof Error) {
        setError(sendError.message);
      } else {
        setError('Could not send message');
      }
    } finally {
      setIsSending(false);
    }
  }

  async function submitQuestion(event) {
    event.preventDefault();
    if (isSending) {
      return;
    }
    await runAgentRequest({
      promptText: question,
      optimisticUserMessage: true,
      resumePartial: false,
    });
  }

  async function resumeLastFailedRequest() {
    if (!lastFailedRequest || isSending) {
      return;
    }

    await runAgentRequest({
      promptText: lastFailedRequest.message,
      conversationIdOverride: lastFailedRequest.conversationId,
      optimisticUserMessage: false,
      resumePartial: true,
    });
  }

  const tierLabel = userProfile?.tier ?? pharmacistSession.tier;
  const usedMessages = userProfile?.monthly_messages_used ?? 0;
  const monthlyLimit = userProfile?.monthly_message_limit ?? 0;
  const remainingMessages = monthlyLimit > 0 ? Math.max(monthlyLimit - usedMessages, 0) : 0;
  const isLimitReached = monthlyLimit > 0 && usedMessages >= monthlyLimit;

  async function reloadConversation() {
    if (!conversationId) {
      return;
    }
    setError('');
    try {
      const response = await getAgentConversation(pharmacistSession.userId, conversationId);
      setConversationMessages(response.messages || []);
      const assistantMessages = (response.messages || []).filter((item) => item.role === 'assistant');
      const lastTurnSender = assistantMessages.length > 0 ? assistantMessages[assistantMessages.length - 1].sender : 'orchestrator-agent';
      setConversationHistory((current) =>
        upsertConversationHistoryEntry(current, {
          conversationId,
          title: current.find((entry) => entry.conversationId === conversationId)?.title || `Conversation ${conversationId.slice(0, 8)}`,
          updatedAt: new Date().toISOString(),
          lastAgent: String(lastTurnSender || 'orchestrator-agent'),
        })
      );
    } catch (reloadError) {
      if (reloadError instanceof Error) {
        setError(reloadError.message);
      } else {
        setError('Could not reload conversation');
      }
    }
  }

  async function openConversation(targetConversationId) {
    setError('');
    try {
      const response = await getAgentConversation(pharmacistSession.userId, targetConversationId);
      setConversationId(targetConversationId);
      setConversationMessages(response.messages || []);
      setChatTurns([]);
      setMessageInfo(`Conversation ID: ${targetConversationId}`);
    } catch (openError) {
      if (openError instanceof Error) {
        setError(openError.message);
      } else {
        setError('Could not open conversation history');
      }
    }
  }

  function startNewConversation() {
    setConversationId('');
    setConversationMessages([]);
    setChatTurns([]);
    setQuestion('');
    setMessageInfo('New conversation draft');
  }

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

  const hasLiveTrace = chatTurns.some((turn) => Array.isArray(turn?.mcp_tool_calls) && turn.mcp_tool_calls.length > 0);
  const finalTraceTurn = chatTurns.length > 0 ? chatTurns[chatTurns.length - 1] : null;
  const displayMessages = (() => {
    const visibleAssistantSenders = new Set([
      'layman-translator-agent',
      'medication-answer-synthesis-agent',
      'orchestrator-agent',
    ]);
    return conversationMessages.filter((item, idx, arr) => {
      if (item?.role !== 'assistant') {
        return true;
      }
      const sender = String(item?.sender || '').trim();
      if (!sender) {
        return idx === arr.length - 1;
      }
      return visibleAssistantSenders.has(sender);
    });
  })();
  const hasMessages = displayMessages.length > 0;
  const hasStartedConversation = Boolean(conversationId || hasMessages || isSending);

  function compactQueryFromInput(input) {
    if (!input || typeof input !== 'object') {
      return '';
    }
    for (const key of ['name', 'medication_name', 'drug_id']) {
      const value = input[key];
      if (typeof value === 'string' && value.trim()) {
        return value.trim();
      }
    }
    return '';
  }

  function renderTurnCard(turn, turnIndex) {
    return (
      <div
        key={`mcp-turn-${turn.agent_id || 'agent'}-${turnIndex}`}
        className="mr-auto w-full max-w-[92%] rounded-2xl border border-secondary/40 bg-secondary/5 p-4"
      >
        <div className="flex items-center gap-2 mb-3">
          <span className="px-2 py-1 rounded-md text-xs font-semibold bg-secondary text-white">MCP Activity</span>
          <span className="text-xs text-on-surface-variant">Live tool orchestration trace</span>
        </div>

        <div className="rounded-xl border border-outline-variant/40 bg-surface p-3">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <p className="text-xs font-semibold text-primary">{turn.agent_id || 'agent'}</p>
            {turn?.step_status === 'running' && (
              <span className="px-2 py-1 rounded-md text-[11px] bg-secondary/15 text-secondary">running</span>
            )}
            {turn?.step_status === 'completed' && (
              <span className="px-2 py-1 rounded-md text-[11px] bg-secondary-container/60 text-secondary">completed</span>
            )}
          </div>
          {turn?.thought_summary && (
            <p className="text-xs text-on-surface-variant mb-2">{turn.thought_summary}</p>
          )}
          {String(turn?.received_input || '').trim() && (
            <details className="mb-2 rounded-lg border border-outline-variant/40 bg-surface-container-low p-2">
              <summary className="cursor-pointer list-none text-xs font-semibold text-on-surface-variant">
                Input received by this phase
              </summary>
              <pre className="mt-2 text-xs whitespace-pre-wrap break-words text-on-surface-variant bg-surface rounded-lg p-2 border border-outline-variant/40">
                {String(turn.received_input)}
              </pre>
            </details>
          )}
          {Array.isArray(turn.mcp_tool_calls) && turn.mcp_tool_calls.length > 0 ? (
            <div className="space-y-2">
              {turn.mcp_tool_calls.map((call, toolIndex) => {
                const compactQuery = compactQueryFromInput(call?.input);
                return (
                  <details key={`${call?.tool_name || 'tool'}-${toolIndex}`} className="rounded-lg border border-outline-variant/40 bg-surface-container-low p-2">
                    <summary className="cursor-pointer list-none">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="px-2 py-1 rounded-md text-xs bg-surface text-on-surface-variant border border-outline-variant/50">{call?.tool_name || 'tool'}</span>
                        <span
                          className={
                            call?.status === 'success'
                              ? 'px-2 py-1 rounded-md text-xs bg-secondary/15 text-secondary'
                              : call?.status === 'warning'
                                ? 'px-2 py-1 rounded-md text-xs bg-tertiary-fixed/30 text-primary'
                                : 'px-2 py-1 rounded-md text-xs bg-error/15 text-error'
                          }
                        >
                          {call?.status || 'unknown'}
                        </span>
                        {compactQuery && <span className="text-xs text-on-surface-variant truncate max-w-[20rem]">query: {compactQuery}</span>}
                      </div>
                    </summary>
                    <div className="mt-2 space-y-2">
                      <pre className="text-xs whitespace-pre-wrap break-words text-on-surface-variant bg-surface rounded-lg p-2 border border-outline-variant/40">
                        {JSON.stringify(call?.input || {}, null, 2)}
                      </pre>
                      <pre className="text-xs whitespace-pre-wrap break-words text-on-surface-variant bg-surface rounded-lg p-2 border border-outline-variant/40">
                        {call?.output ? JSON.stringify(call.output, null, 2) : (call?.output_summary || 'No output')}
                      </pre>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-on-surface-variant">Waiting for MCP calls...</p>
          )}
          {String(turn?.response || turn?.stage_output || '').trim() && (
            <details className="mt-2 rounded-lg border border-outline-variant/40 bg-surface-container-low p-2">
              <summary className="cursor-pointer list-none text-xs font-semibold text-on-surface-variant">
                Output produced by this phase
              </summary>
              <pre className="mt-2 text-xs whitespace-pre-wrap break-words text-on-surface-variant bg-surface rounded-lg p-2 border border-outline-variant/40">
                {String(turn.response || turn.stage_output)}
              </pre>
            </details>
          )}
          {String(turn?.next_stage_input || turn?.response || '').trim() && (
            <details className="mt-2 rounded-lg border border-outline-variant/40 bg-surface-container-low p-2">
              <summary className="cursor-pointer list-none text-xs font-semibold text-on-surface-variant">
                Input sent to next phase
              </summary>
              <pre className="mt-2 text-xs whitespace-pre-wrap break-words text-on-surface-variant bg-surface rounded-lg p-2 border border-outline-variant/40">
                {String(turn.next_stage_input || turn.response)}
              </pre>
            </details>
          )}
        </div>
      </div>
    );
  }

  function renderComposer(extraClass = '') {
    return (
      <form className={`space-y-1.5 ${extraClass}`.trim()} onSubmit={submitQuestion}>
        {!hasStartedConversation && (
          <div className="rounded-lg border border-outline-variant/40 bg-surface-container-low p-1.5">
            <p className="text-[10px] text-on-surface-variant">
              The orchestrator automatically selects and chains agents based on your query.
            </p>
          </div>
        )}

        <textarea
          className="w-full min-h-16 rounded-lg border-outline-variant/60 bg-surface px-2.5 py-1.5 text-xs"
          placeholder="Example: Ce stii despre metamizol? verifica interactiunile si explica pe intelesul pacientului."
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={2}
        />

        <div className="flex flex-wrap gap-2">
          <button
            className="bg-primary-container text-white px-3 py-1.5 rounded-lg text-[11px] font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
            type="submit"
            disabled={isSending || isLimitReached}
          >
            {isSending ? 'Sending...' : 'Ask Agent'}
          </button>
          {lastFailedRequest && (
            <button
              className="px-3 py-1.5 rounded-lg text-[11px] font-bold border border-secondary/40 bg-secondary/10 text-secondary disabled:opacity-70"
              type="button"
              onClick={resumeLastFailedRequest}
              disabled={isSending}
            >
              Resume Last Request
            </button>
          )}
          <button
            className="px-3 py-1.5 rounded-lg text-[11px] font-bold border border-outline-variant/60 bg-surface"
            type="button"
            onClick={reloadConversation}
            disabled={!conversationId}
          >
            Reload Session Trace
          </button>
        </div>
      </form>
    );
  }

  return (
    <main className="bg-surface-container-low min-h-[calc(100vh-80px)]">
      <section className="w-full h-[calc(100vh-80px)]">
        <div className="w-full h-full flex flex-col lg:flex-row gap-0">
          <aside className="lg:w-80 w-full bg-surface-container-lowest p-6 border-b lg:border-b-0 lg:border-r border-outline-variant/40 overflow-y-auto">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-1">Chat History</p>
                <h2 className="text-xl text-primary font-bold">Pharmacist Agent</h2>
              </div>
              <button
                type="button"
                onClick={startNewConversation}
                className="px-3 py-2 rounded-xl text-xs font-bold bg-primary-container text-white"
              >
                New Chat
              </button>
            </div>

            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low p-4 mb-4">
              <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Signed In</p>
              <p className="text-sm font-semibold text-primary">{pharmacistSession.fullName}</p>
              <p className="text-xs text-on-surface-variant break-all mt-1">{pharmacistSession.email}</p>
            </div>

            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
              {conversationHistory.length > 0 ? (
                conversationHistory.map((entry) => (
                  <button
                    key={entry.conversationId}
                    type="button"
                    onClick={() => openConversation(entry.conversationId)}
                    className={
                      conversationId === entry.conversationId
                        ? 'w-full text-left rounded-xl border border-secondary bg-secondary/10 p-3'
                        : 'w-full text-left rounded-xl border border-outline-variant/40 bg-surface p-3 hover:bg-surface-container-low'
                    }
                  >
                    <p className="text-sm font-semibold text-primary truncate">{entry.title}</p>
                    <p className="text-xs text-on-surface-variant mt-1 truncate">{entry.lastAgent || 'Agent unknown'}</p>
                    <p className="text-[11px] text-on-surface-variant mt-1">{new Date(entry.updatedAt).toLocaleString()}</p>
                  </button>
                ))
              ) : (
                <div className="rounded-xl border border-outline-variant/40 bg-surface p-3 text-xs text-on-surface-variant">
                  No conversations yet. Start your first chat.
                </div>
              )}
            </div>

            <a
              className="mt-4 inline-flex px-4 py-2 rounded-xl text-sm font-bold bg-surface-container-low hover:bg-surface-container-high transition-colors"
              href="/pharmacist/account"
            >
              Account Settings
            </a>
          </aside>

          <div className="flex-1 min-w-0 bg-surface-container-lowest p-3 lg:p-4 border-l-0 border-outline-variant/40 flex flex-col">
            {!hasStartedConversation && (
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-1">Dedicated Chat Route</p>
                  <h3 className="text-2xl text-primary font-bold">Orchestrated Agent Chat</h3>
                </div>
                <div className="rounded-lg border border-outline-variant/40 bg-surface px-2 py-1.5">
                  <p className="text-[10px] uppercase tracking-wider text-on-surface-variant">Conversation</p>
                  <p className="text-[11px] font-semibold text-primary break-all">{conversationId || 'Not started'}</p>
                </div>
              </div>
            )}

            {messageInfo && !hasStartedConversation && <p className="mt-4 text-sm font-semibold text-secondary">{messageInfo}</p>}
            {error && <p className="mt-2 text-sm font-semibold text-error">{error}</p>}

            <div className="mt-2 flex-1 space-y-3 overflow-y-auto min-h-0">
              {displayMessages.length === 0 && !hasLiveTrace && !isSending ? (
                <div className="rounded-2xl border border-outline-variant/50 bg-surface p-4 text-sm text-on-surface-variant">
                  No chat turns yet. Send a message to start a tracked conversation.
                </div>
              ) : (
                (() => {
                  const timeline = [];
                  let assistantTurnIndex = 0;

                  displayMessages.forEach((message, index) => {
                    if (message.role === 'assistant' && assistantTurnIndex < chatTurns.length) {
                      timeline.push(renderTurnCard(chatTurns[assistantTurnIndex], assistantTurnIndex));
                      assistantTurnIndex += 1;
                    }

                    timeline.push(
                      <div
                        key={`${message.timestamp || index}-${index}`}
                        className={
                          message.role === 'user'
                            ? 'ml-auto max-w-[85%] rounded-2xl border border-secondary/40 bg-secondary/10 p-4'
                            : 'mr-auto max-w-[90%] rounded-2xl border border-outline-variant/40 bg-surface p-4'
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
                        <div className="prose prose-sm max-w-none text-on-surface-variant">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {normalizeMarkdownContent(message.content || '')}
                          </ReactMarkdown>
                        </div>
                      </div>
                    );
                  });

                  while (assistantTurnIndex < chatTurns.length) {
                    timeline.push(renderTurnCard(chatTurns[assistantTurnIndex], assistantTurnIndex));
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

            {renderComposer('mt-1.5')}
          </div>
        </div>
      </section>
    </main>
  );
}

function PharmacistAccountPage({ pharmacistSession, onLogout, onSessionRefresh }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function handlePasswordChange(event) {
    event.preventDefault();
    setMessage('');
    setError('');

    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match');
      return;
    }

    setBusy(true);
    try {
      await changeMyPassword(pharmacistSession.userId, currentPassword, newPassword);
      setMessage('Password updated successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      await onSessionRefresh();
    } catch (passwordError) {
      if (passwordError instanceof Error) {
        setError(passwordError.message);
      } else {
        setError('Could not update password');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-4xl mx-auto grid md:grid-cols-2 gap-6">
          <div className="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
            <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Account</p>
            <h2 className="text-3xl text-primary font-bold mb-4">Your Profile</h2>
            <p className="text-sm text-on-surface-variant mb-6">Manage your session and account security settings.</p>

            <div className="space-y-3 mb-6">
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Name</p>
                <p className="text-primary font-semibold">{pharmacistSession.fullName}</p>
              </div>
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Email</p>
                <p className="text-primary font-semibold break-all">{pharmacistSession.email}</p>
              </div>
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Tier</p>
                <p className="text-primary font-semibold uppercase">{pharmacistSession.tier}</p>
              </div>
            </div>

            <div className="flex gap-3">
              <a className="px-4 py-2 rounded-xl text-sm font-bold bg-surface-container-low hover:bg-surface-container-high transition-colors" href="/pharmacist/chat">
                Back to Agent
              </a>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-error hover:bg-error/10 transition-colors"
                type="button"
                onClick={onLogout}
              >
                Log Out
              </button>
            </div>
          </div>

          <div className="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
            <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Security</p>
            <h3 className="text-2xl text-primary font-bold mb-4">Change Password</h3>

            <form className="space-y-4" onSubmit={handlePasswordChange}>
              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Current Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                />
              </label>

              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">New Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  minLength={6}
                  required
                />
              </label>

              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Confirm New Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  minLength={6}
                  required
                />
              </label>

              {message && <p className="text-sm font-semibold text-secondary">{message}</p>}
              {error && <p className="text-sm font-semibold text-error">{error}</p>}

              <button
                className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
                type="submit"
                disabled={busy}
              >
                {busy ? 'Updating...' : 'Update Password'}
              </button>
            </form>
          </div>
        </div>
      </section>
    </main>
  );
}

function LandingPageContent() {
  return (
    <main>
      <section className="relative pt-24 pb-32 px-8 overflow-hidden">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-12 gap-16 items-center">
          <div className="lg:col-span-7 z-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-secondary-container/30 text-secondary rounded-full mb-6">
              <span className="material-symbols-outlined text-sm">auto_awesome</span>
              <span className="text-xs font-bold uppercase tracking-wider">Next-Gen Clinical Intelligence</span>
            </div>
            <h1 className="text-5xl md:text-7xl font-bold text-primary mb-8 leading-[1.1]">
              Intelligent Pharmaceutical Advice, <span className="text-secondary italic">Tailored</span> for Your Pharmacy.
            </h1>
            <p className="text-lg text-on-surface-variant mb-10 max-w-2xl leading-relaxed">
              Leverage proprietary machine learning to transform massive clinical databases into actionable insights. Accuracy at the speed of thought.
            </p>
            <div className="flex flex-wrap gap-4">
              <button className="px-8 py-4 bg-primary-container text-white rounded-2xl font-bold text-lg flex items-center gap-2 shadow-lg shadow-primary-container/20 hover:scale-[0.98] transition-all" type="button">
                Request a Demo
                <span className="material-symbols-outlined">arrow_forward</span>
              </button>
              <a
                className="px-8 py-4 bg-surface-container-low text-primary rounded-2xl font-bold text-lg hover:bg-surface-container-high transition-colors"
                href="/admin"
              >
                Manage Users
              </a>
            </div>
          </div>
          <div className="lg:col-span-5 relative">
            <div className="aspect-square rounded-3xl bg-surface-container-lowest shadow-2xl overflow-hidden relative border border-outline-variant/10">
              <img
                alt="Laboratory technology"
                className="object-cover w-full h-full opacity-90"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDZJHRgEl-J6hcTFzy6K9mwe1LFwdfgWP-k_YG2DLx36F1VuPsMuVx7zhOSkDwAJB5PxwjMww_0Qh2SL0WzLmFcu0e2fKk7l-z7Z6XG6UAhnmp59TkvKEmkDGGtrTB-cNaFLincythus-B-uPCdbO7YjRMJ6w2Ky447eIp6h8q-KDmHzZRVBq-GR6AIQja_8lnpBJCFzxIj5xs1QI2bh8gQnBVOwTn_z1ADRWrWFR4O_LlBOziOvKRgPiGnGwNyKsHNlBgqY9aquE8"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent"></div>
              <div className="absolute bottom-6 left-6 right-6 bg-surface-container-lowest/80 backdrop-blur-xl p-4 rounded-2xl border-l-4 border-secondary flex items-start gap-3 shadow-xl">
                <span className="material-symbols-outlined text-secondary">verified_user</span>
                <div>
                  <p className="text-xs font-bold text-primary uppercase tracking-tighter">AI Verification Success</p>
                  <p className="text-sm text-on-surface-variant">Drug interaction database updated 2m ago.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute top-0 right-0 -z-10 w-1/3 h-full bg-gradient-to-l from-secondary-container/10 to-transparent blur-3xl"></div>
      </section>

      <section className="py-24 px-8 bg-surface-container-low">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-4xl font-bold text-primary mb-4">The Clinical Edge</h2>
            <p className="text-on-surface-variant max-w-xl">
              Precision-engineered tools designed to automate complex pharmaceutical workflows.
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 bg-surface-container-lowest p-10 rounded-3xl shadow-sm border-t-4 border-secondary flex flex-col justify-between group">
              <div>
                <div className="w-12 h-12 bg-surface-container-low rounded-xl flex items-center justify-center mb-6 group-hover:bg-secondary-container transition-colors">
                  <span className="material-symbols-outlined text-secondary">database</span>
                </div>
                <h3 className="text-3xl font-bold text-primary mb-4">Automated Clinical Intelligence</h3>
                <p className="text-on-surface-variant text-lg leading-relaxed max-w-lg">
                  Our autonomous agents continuously scrape globally recognized public databases and academic journals, extracting critical drug information with near-zero latency.
                </p>
              </div>
              <div className="mt-12 flex gap-4">
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">Live Scraping</div>
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">NLP Extraction</div>
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">Validation Engine</div>
              </div>
            </div>
            <div className="bg-primary text-on-primary p-10 rounded-3xl shadow-sm flex flex-col justify-center relative overflow-hidden">
              <div className="relative z-10">
                <span className="material-symbols-outlined text-secondary-fixed mb-6 text-4xl">psychology</span>
                <h3 className="text-2xl font-bold mb-4">Reasoning Engine</h3>
                <p className="text-primary-fixed-dim text-sm leading-relaxed">
                  Beyond simple search, our AI reasons through contraindications and dosage efficacy in real-time.
                </p>
              </div>
              <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-secondary/20 rounded-full blur-3xl"></div>
            </div>
            <div className="bg-surface-container-lowest p-10 rounded-3xl shadow-sm flex flex-col justify-between group">
              <div>
                <div className="w-12 h-12 bg-surface-container-low rounded-xl flex items-center justify-center mb-6 group-hover:bg-secondary-container transition-colors">
                  <span className="material-symbols-outlined text-secondary">medication</span>
                </div>
                <h3 className="text-2xl font-bold text-primary mb-4">Tailored Recommendations</h3>
                <p className="text-on-surface-variant text-sm leading-relaxed">
                  Personalized drug suggestions based on specific patient demographics, history, and real-time biometric inputs.
                </p>
              </div>
              <a className="mt-8 text-secondary font-bold text-sm flex items-center gap-2" href="#">
                Learn more
                <span className="material-symbols-outlined text-xs">open_in_new</span>
              </a>
            </div>
            <div className="md:col-span-2 bg-surface-container-lowest p-10 rounded-3xl shadow-sm flex flex-col md:flex-row gap-10 items-center overflow-hidden">
              <div className="flex-1">
                <h3 className="text-2xl font-bold text-primary mb-4">Interoperable API Design</h3>
                <p className="text-on-surface-variant text-sm leading-relaxed mb-6">
                  Integrate our intelligence into your existing EHR or pharmacy management system with ease. Our drug database API is built for high-performance enterprise applications.
                </p>
                <button className="text-primary font-bold text-sm underline underline-offset-4 decoration-secondary decoration-2" type="button">
                  View API Documentation
                </button>
              </div>
              <div className="flex-1 w-full bg-surface-container-low rounded-2xl p-6 font-mono text-xs text-on-surface-variant relative">
                <div className="flex gap-1.5 mb-4">
                  <div className="w-2 h-2 rounded-full bg-error/40"></div>
                  <div className="w-2 h-2 rounded-full bg-tertiary-fixed-dim"></div>
                  <div className="w-2 h-2 rounded-full bg-secondary-fixed-dim"></div>
                </div>
                <code className="block">GET /v1/recommendations</code>
                <code className="block text-secondary">{'{'}</code>
                <code className="block ml-4">&quot;patient_id&quot;: &quot;PX-902&quot;,</code>
                <code className="block ml-4">&quot;analysis&quot;: &quot;active&quot;,</code>
                <code className="block ml-4 text-primary-fixed-dim italic">// clinical inference...</code>
                <code className="block text-secondary">{'}'}</code>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-8">
        <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-20 items-center">
          <div className="relative">
            <div className="rounded-3xl overflow-hidden aspect-[4/5] shadow-2xl">
              <img
                alt="Professional analyzing data"
                className="w-full h-full object-cover"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDqzn7b5rH3BXVKDtI0HPGwkyY7o-nPxiUnTTOA3XDh3HJBmC7x9PPCpc-VCH7oK0XuBEn9SiRPq7vYDa_I0psOjwevXYA2fZiEoFZZ7MD8mmv3Apkaic33lhl8WnCtIAEwFEBzwn8pTemKXiOUUzVCA1cDkaaxF4erdzJhvUewTGi1VFvDVfWkwdnPyi1MiXEgBkQgQHfbPl0Z716b_ga-8dRQ7vORqOs_H4x0sQSFy2W7lCE0k6kjT856C2Jwc2qiPx9UgmJGj4g"
              />
            </div>
            <div className="absolute -bottom-8 -right-8 bg-surface-container-lowest p-8 rounded-3xl shadow-xl max-w-xs border border-outline-variant/10">
              <p className="font-headline italic text-primary text-xl mb-4 leading-tight">
                &quot;The accuracy is unprecedented in the B2B space.&quot;
              </p>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-secondary-container"></div>
                <div>
                  <p className="text-sm font-bold">Dr. Sarah Chen</p>
                  <p className="text-xs text-on-surface-variant">Director of Innovation</p>
                </div>
              </div>
            </div>
          </div>
          <div>
            <h2 className="text-4xl font-bold text-primary mb-6 leading-tight">
              From Raw Data to <span className="text-secondary italic">Patient Success</span>.
            </h2>
            <p className="text-on-surface-variant text-lg leading-relaxed mb-8">
              The pharmaceutical landscape shifts daily. New trials, drug recalls, and dosage guidelines emerge faster than any human can track. PharmacoAI provides the intellectual infrastructure to keep your practice ahead of the curve.
            </p>
            <ul className="space-y-6">
              <li className="flex items-start gap-4">
                <div className="w-6 h-6 rounded-full bg-secondary/10 flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="material-symbols-outlined text-secondary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check_circle
                  </span>
                </div>
                <div>
                  <h4 className="font-bold text-primary">Contextual Awareness</h4>
                  <p className="text-sm text-on-surface-variant">Our models understand the clinical context, not just keywords.</p>
                </div>
              </li>
              <li className="flex items-start gap-4">
                <div className="w-6 h-6 rounded-full bg-secondary/10 flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="material-symbols-outlined text-secondary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check_circle
                  </span>
                </div>
                <div>
                  <h4 className="font-bold text-primary">Regulatory Alignment</h4>
                  <p className="text-sm text-on-surface-variant">Built-in compliance monitoring for FDA and EMA updates.</p>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="py-20 px-8">
        <div className="max-w-5xl mx-auto bg-primary-container rounded-[2.5rem] p-12 md:p-20 text-center relative overflow-hidden">
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">Ready to upgrade your pharmacy&apos;s intelligence?</h2>
            <p className="text-on-primary-container text-lg mb-10 max-w-2xl mx-auto">
              Join the 500+ clinical institutions leveraging PharmacoAI to drive better patient outcomes through automation.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button className="bg-secondary text-white px-10 py-4 rounded-2xl font-bold text-lg hover:bg-on-secondary-container transition-colors shadow-lg shadow-secondary/20" type="button">
                Request Demo
              </button>
              <button className="bg-white/10 text-white backdrop-blur-md px-10 py-4 rounded-2xl font-bold text-lg hover:bg-white/20 transition-colors" type="button">
                Contact Sales
              </button>
            </div>
          </div>
          <div className="absolute inset-0 -z-0 opacity-10">
            <div className="absolute top-0 left-0 w-64 h-64 bg-secondary rounded-full blur-[100px]"></div>
            <div className="absolute bottom-0 right-0 w-64 h-64 bg-primary-fixed rounded-full blur-[100px]"></div>
          </div>
        </div>
      </section>
    </main>
  );
}

function SiteFooter() {
  return (
    <footer className="bg-slate-100 dark:bg-slate-900 border-t-0">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 w-full px-8 py-12 max-w-7xl mx-auto">
        <div className="lg:col-span-1">
          <div className="font-serif text-lg font-bold text-slate-800 dark:text-slate-200 mb-6">PharmacoAI</div>
          <p className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 leading-relaxed">
            Elevating the standard of care through rigorous clinical machine learning and data extraction.
          </p>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Product</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Drug Database API
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Solutions
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Pricing
            </a>
          </div>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Legal</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Compliance
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Privacy Policy
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Terms of Service
            </a>
          </div>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Support</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Contact Support
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Help Center
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Documentation
            </a>
          </div>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-8 py-8 border-t border-slate-200 dark:border-slate-800 flex flex-col md:flex-row justify-between items-center gap-4">
        <p className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400">
          &copy; 2026 PharmacoAI. All clinical insights powered by proprietary machine learning.
        </p>
        <div className="flex gap-6">
          <span className="material-symbols-outlined text-slate-400 cursor-pointer hover:text-teal-700 transition-colors">share</span>
          <span className="material-symbols-outlined text-slate-400 cursor-pointer hover:text-teal-700 transition-colors">podcasts</span>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '/';
  const isAdminRoute = pathname.startsWith('/admin');
  const isPharmacistRoute = pathname.startsWith('/pharmacist');
  const isPharmacistAccountRoute = pathname.startsWith('/pharmacist/account');
  const isPharmacistChatRoute = pathname.startsWith('/pharmacist/chat') || pathname.startsWith('/pharmacist/agent');
  const isPharmacistRootRoute = pathname === '/pharmacist';
  const currentRoute = isAdminRoute ? 'admin' : isPharmacistRoute ? 'pharmacist' : 'landing';

  const [adminSession, setAdminSession] = useState(() => readAdminSession());
  const [pharmacistSession, setPharmacistSession] = useState(() => readPharmacistSession());

  async function handleAdminLogin({ username, password }) {
    const email = username.includes('@') ? username : ADMIN_LOGIN_EMAIL;
    const user = await loginUser(email, password);

    if (user.role !== 'admin') {
      throw new Error('This account is not an admin account');
    }

    const session = {
      userId: user.user_id,
      username,
      email: user.email,
    };

    persistAdminSession(session);
    setAdminSession(session);
  }

  function handleLogout() {
    clearAdminSession();
    setAdminSession(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  async function handlePharmacistLogin({ email, password }) {
    const user = await loginUser(email, password);

    if (user.role !== 'pharmacist') {
      throw new Error('This account is not a pharmacist account');
    }

    const session = {
      userId: user.user_id,
      email: user.email,
      fullName: user.full_name,
      tier: user.tier,
    };

    persistPharmacistSession(session);
    setPharmacistSession(session);

    if (typeof window !== 'undefined') {
      window.location.href = '/pharmacist/chat';
    }
  }

  function handlePharmacistLogout() {
    clearPharmacistSession();
    setPharmacistSession(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  async function refreshPharmacistSession() {
    if (!pharmacistSession?.userId) {
      return;
    }

    const user = await getMyUser(pharmacistSession.userId);
    const session = {
      userId: user.id,
      email: user.email,
      fullName: user.full_name,
      tier: user.tier,
    };
    persistPharmacistSession(session);
    setPharmacistSession(session);
  }

  return (
    <div className="text-on-surface selection:bg-secondary-container selection:text-on-secondary-container">
      <TopNav
        currentRoute={currentRoute}
        isAdminAuthenticated={Boolean(adminSession)}
        isPharmacistAuthenticated={Boolean(pharmacistSession)}
        onAdminLogout={handleLogout}
      />
      {isAdminRoute ? (
        adminSession ? (
          <main>
            <AdminUsersPanel adminId={adminSession.userId} />
          </main>
        ) : (
          <AdminLoginPage onLogin={handleAdminLogin} />
        )
      ) : isPharmacistRoute ? (
        pharmacistSession ? (
          isPharmacistAccountRoute ? (
            <PharmacistAccountPage
              pharmacistSession={pharmacistSession}
              onLogout={handlePharmacistLogout}
              onSessionRefresh={refreshPharmacistSession}
            />
          ) : isPharmacistChatRoute || isPharmacistRootRoute ? (
            <PharmacistChatPage pharmacistSession={pharmacistSession} />
          ) : (
            <PharmacistChatPage pharmacistSession={pharmacistSession} />
          )
        ) : (
          <PharmacistLoginPage onLogin={handlePharmacistLogin} />
        )
      ) : (
        <LandingPageContent />
      )}
      <SiteFooter />
    </div>
  );
}
