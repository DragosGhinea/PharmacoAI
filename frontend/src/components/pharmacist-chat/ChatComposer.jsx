export default function ChatComposer({
  question,
  isSending,
  isLimitReached,
  hasStartedConversation,
  hasFailedRequest,
  onQuestionChange,
  onSubmit,
  onResumeLastRequest,
  onReload,
  hasConversationId,
  onStop,
}) {
  return (
    <form className="space-y-1.5 mt-1.5" onSubmit={onSubmit}>
      {!hasStartedConversation && (
        <div className="rounded-lg border border-outline-variant/40 bg-surface-container-low p-1.5">
          <p className="text-[10px] text-on-surface-variant">
            The orchestrator automatically selects and chains agents based on your query.
          </p>
        </div>
      )}

      <textarea
        className="w-full min-h-16 rounded-lg border-outline-variant/60 bg-surface px-2.5 py-1.5 text-xs disabled:opacity-70"
        placeholder="Example: Ce stii despre metamizol? verifica interactiunile si explica pe intelesul pacientului."
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        disabled={isSending}
        aria-disabled={isSending}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!isSending && !isLimitReached && typeof onSubmit === 'function') {
              onSubmit({ preventDefault: () => {} });
            }
          }
        }}
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
        <button
          className="px-3 py-1.5 rounded-lg text-[11px] font-bold border border-error/50 bg-error/10 text-error disabled:opacity-50"
          type="button"
          onClick={onStop}
          disabled={!isSending}
        >
          Stop
        </button>
        {hasFailedRequest && (
          <button
            className="px-3 py-1.5 rounded-lg text-[11px] font-bold border border-secondary/40 bg-secondary/10 text-secondary disabled:opacity-70"
            type="button"
            onClick={onResumeLastRequest}
            disabled={isSending}
          >
            Resume Last Request
          </button>
        )}
        <button
          className="px-3 py-1.5 rounded-lg text-[11px] font-bold border border-outline-variant/60 bg-surface"
          type="button"
          onClick={onReload}
          disabled={!hasConversationId}
        >
          Reload Session Trace
        </button>
      </div>
    </form>
  );
}
