import { useEffect, useState } from 'react';

import {
  cancelOrchestratorStream,
  chatWithOrchestratorStream,
  deleteAllConversations,
  deleteConversation,
  getAgentConversation,
  getMyUser,
} from '../api/usersApi';
import ChatComposer from '../components/pharmacist-chat/ChatComposer';
import ChatSidebar from '../components/pharmacist-chat/ChatSidebar';
import ChatTimeline from '../components/pharmacist-chat/ChatTimeline';
import {
  hasVisibleTimelineMessages,
  persistPharmacistChatHistory,
  readPharmacistChatHistory,
  upsertConversationHistoryEntry,
} from '../utils/pharmacistChatUtils';

export default function PharmacistChatPage({ pharmacistSession }) {
  const [question, setQuestion] = useState('');
  const [userProfile, setUserProfile] = useState(null);
  const [error, setError] = useState('');
  const [messageInfo, setMessageInfo] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [lastFailedRequest, setLastFailedRequest] = useState(null);
  const [conversationId, setConversationId] = useState('');
  const [chatTurns, setChatTurns] = useState([]);
  const [activeAssistantBaseIndex, setActiveAssistantBaseIndex] = useState(0);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [conversationHistory, setConversationHistory] = useState(() => readPharmacistChatHistory(pharmacistSession.userId));
  const [isCompactMode, setIsCompactMode] = useState(false);
  const [streamAbortController, setStreamAbortController] = useState(null);
  const [streamRequestId, setStreamRequestId] = useState('');
  const [agentWorkHistory, setAgentWorkHistory] = useState([]);

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
      const streamId = call?.stream_id;
      let updatedCalls = [...existingCalls];
      if (streamId) {
        const replaceIndex = updatedCalls.findIndex((item) => item?.stream_id === streamId);
        if (replaceIndex >= 0) {
          updatedCalls[replaceIndex] = {
            ...updatedCalls[replaceIndex],
            ...call,
          };
        } else {
          updatedCalls.push(call);
        }
      } else {
        updatedCalls.push(call);
      }

      next[turnIndex] = {
        ...existingTurn,
        agent_id: existingTurn.agent_id || agentId,
        step_status: existingTurn.step_status || 'running',
        mcp_tool_calls: updatedCalls,
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
      if (status === 'running' && turnIndex > 0) {
        for (let i = 0; i < turnIndex; i += 1) {
          if (next[i]?.step_status === 'running') {
            next[i] = {
              ...next[i],
              step_status: 'completed',
            };
          }
        }
      }
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
    const assistantBaseIndexSnapshot = conversationMessages.filter((item) => item?.role === 'assistant').length;
    setActiveAssistantBaseIndex(assistantBaseIndexSnapshot);

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

    const abortController = new AbortController();
    setStreamAbortController(abortController);
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
          if (event?.type === 'started' && typeof event?.request_id === 'string') {
            setStreamRequestId(event.request_id);
            return;
          }
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
            const stageOutput = String(event?.stage_output || '').trim();
            const stageAgent = String(event?.agent_id || 'agent');
            if (stageOutput) {
              const provisionalTimestamp = new Date().toISOString();
              setConversationMessages((current) => {
                const fingerprint = `${stageAgent}|${stageOutput}`;
                const alreadyPresent = current.some(
                  (item) => item?.role === 'assistant' && `${String(item?.sender || 'assistant')}|${String(item?.content || '').trim()}` === fingerprint
                );
                if (alreadyPresent) {
                  return current;
                }
                return [
                  ...current,
                  {
                    role: 'assistant',
                    sender: stageAgent,
                    content: stageOutput,
                    timestamp: provisionalTimestamp,
                  },
                ];
              });
            }
          }
        },
        {
          signal: abortController.signal,
        }
      );

      const resolvedConversationId = response.conversation_id || targetConversationId || '';
      setConversationId(resolvedConversationId);
      setChatTurns(response.turns || []);
      setAgentWorkHistory(response.agent_work_history || []);
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
        setAgentWorkHistory(conversationResponse.agent_work_history || []);
      }

      const refreshedProfile = await getMyUser(pharmacistSession.userId);
      setUserProfile(refreshedProfile);
      setLastFailedRequest(null);
    } catch (sendError) {
      if (sendError?.name === 'AbortError') {
        setMessageInfo('Request cancelled');
        return;
      }
      setLastFailedRequest(failedRequestContext);
      if (sendError instanceof Error) {
        setError(sendError.message);
      } else {
        setError('Could not send message');
      }
    } finally {
      setChatTurns([]);
      setStreamRequestId('');
      setStreamAbortController(null);
      setIsSending(false);
    }
  }

  function stopActiveRequest() {
    if (streamRequestId) {
      cancelOrchestratorStream(pharmacistSession.userId, streamRequestId).catch(() => null);
    }
    if (streamAbortController) {
      streamAbortController.abort();
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
      setAgentWorkHistory(response.agent_work_history || []);
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
      setAgentWorkHistory(response.agent_work_history || []);
      setActiveAssistantBaseIndex(0);
      setChatTurns([]);
      setAgentWorkHistory([]);
      setMessageInfo(`Conversation ID: ${targetConversationId}`);
    } catch (openError) {
      if (openError instanceof Error) {
        setError(openError.message);
      } else {
        setError('Could not open conversation history');
      }
    }
  }

  async function removeConversation(targetConversationId) {
    if (!targetConversationId) {
      return;
    }
    setError('');
    try {
      await deleteConversation(pharmacistSession.userId, targetConversationId);
      setConversationHistory((current) =>
        current.filter((entry) => entry.conversationId !== targetConversationId)
      );
      if (conversationId === targetConversationId) {
        startNewConversation();
      }
    } catch (deleteError) {
      if (deleteError instanceof Error) {
        setError(deleteError.message);
      } else {
        setError('Could not delete conversation');
      }
    }
  }

  async function removeAllConversations() {
    setError('');
    try {
      await deleteAllConversations(pharmacistSession.userId);
      setConversationHistory([]);
      startNewConversation();
    } catch (deleteError) {
      if (deleteError instanceof Error) {
        setError(deleteError.message);
      } else {
        setError('Could not delete conversations');
      }
    }
  }

  function startNewConversation() {
    setConversationId('');
    setConversationMessages([]);
    setActiveAssistantBaseIndex(0);
    setChatTurns([]);
    setAgentWorkHistory([]);
    setQuestion('');
    setMessageInfo('New conversation draft');
  }

  const hasLiveTrace = chatTurns.some((turn) => Array.isArray(turn?.mcp_tool_calls) && turn.mcp_tool_calls.length > 0);
  const hasMessages = hasVisibleTimelineMessages(conversationMessages);
  const hasStartedConversation = Boolean(conversationId || hasMessages || isSending);

  return (
    <main className="bg-surface-container-low min-h-[calc(100vh-80px)]">
      <section className="w-full h-[calc(100vh-80px)]">
        <div className="w-full h-full flex flex-col lg:flex-row gap-0">
          <ChatSidebar
            pharmacistSession={pharmacistSession}
            tierLabel={tierLabel}
            usedMessages={usedMessages}
            monthlyLimit={monthlyLimit}
            remainingMessages={remainingMessages}
            conversationHistory={conversationHistory}
            conversationId={conversationId}
            onOpenConversation={openConversation}
            onNewConversation={startNewConversation}
            onDeleteConversation={removeConversation}
            onDeleteAllConversations={removeAllConversations}
          />

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

            <div className="flex items-center justify-between gap-3 mb-2">
              <div className="text-xs text-on-surface-variant">View mode</div>
              <button
                type="button"
                onClick={() => setIsCompactMode((current) => !current)}
                className="px-3 py-1.5 rounded-full text-xs font-semibold border border-outline-variant/50 bg-surface text-on-surface-variant"
              >
                {isCompactMode ? 'Expanded messages' : 'Compact messages'}
              </button>
            </div>

            <ChatTimeline
              conversationMessages={conversationMessages}
              chatTurns={chatTurns}
              agentWorkHistory={agentWorkHistory}
              assistantBaseIndex={activeAssistantBaseIndex}
              hasLiveTrace={hasLiveTrace}
              isSending={isSending}
              compactMode={isCompactMode}
            />

            <ChatComposer
              question={question}
              isSending={isSending}
              isLimitReached={isLimitReached}
              hasStartedConversation={hasStartedConversation}
              hasFailedRequest={Boolean(lastFailedRequest)}
              onQuestionChange={setQuestion}
              onSubmit={submitQuestion}
              onResumeLastRequest={resumeLastFailedRequest}
              onReload={reloadConversation}
              hasConversationId={Boolean(conversationId)}
              onStop={stopActiveRequest}
            />
          </div>
        </div>
      </section>
    </main>
  );
}
