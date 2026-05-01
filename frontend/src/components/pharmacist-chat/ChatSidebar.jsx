export default function ChatSidebar({
  pharmacistSession,
  tierLabel,
  usedMessages,
  monthlyLimit,
  remainingMessages,
  addonMessages = 0,
  conversationHistory,
  conversationId,
  onOpenConversation,
  onNewConversation,
  onDeleteConversation,
  onDeleteAllConversations,
}) {
  return (
    <aside className="lg:w-80 w-full bg-surface-container-lowest p-6 border-b lg:border-b-0 lg:border-r border-outline-variant/40 flex flex-col min-h-0">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-1">Chat History</p>
          <h2 className="text-xl text-primary font-bold">Pharmacist Agent</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onNewConversation}
            className="px-3 py-2 rounded-xl text-xs font-bold bg-primary-container text-white"
          >
            New Chat
          </button>
          <button
            type="button"
            onClick={onDeleteAllConversations}
            className="px-3 py-2 rounded-xl text-xs font-bold border border-error/50 text-error bg-error/10"
          >
            Delete All
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low p-4 mb-4">
        <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Signed In</p>
        <p className="text-sm font-semibold text-primary">{pharmacistSession.fullName}</p>
        <p className="text-xs text-on-surface-variant break-all mt-1">{pharmacistSession.email}</p>
      </div>

      <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low p-4 mb-4">
        <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Usage</p>
        <p className="text-sm font-semibold text-primary uppercase">Tier: {tierLabel}</p>
        <p className="text-xs text-on-surface-variant mt-1">{usedMessages}/{monthlyLimit || 'unlimited'} messages used</p>
        {monthlyLimit > 0 && (
          <p className="text-xs text-on-surface-variant mt-1">Remaining this month: {remainingMessages}</p>
        )}
        {addonMessages > 0 && (
          <p className="text-xs font-semibold text-secondary mt-2">+{addonMessages} add-on messages</p>
        )}
        {monthlyLimit > 0 && remainingMessages === 0 && addonMessages === 0 && (
          <a
            href="/pharmacist/account#addons"
            className="mt-3 inline-flex w-full justify-center px-3 py-2 rounded-xl text-xs font-bold bg-primary-container text-white"
          >
            Buy More Messages
          </a>
        )}
      </div>

      <div className="space-y-2 flex-1 min-h-0 overflow-y-auto pr-1">
        {conversationHistory.length > 0 ? (
          conversationHistory.map((entry) => (
            <div
              key={entry.conversationId}
              className={
                conversationId === entry.conversationId
                  ? 'w-full rounded-xl border border-secondary bg-secondary/10 p-3'
                  : 'w-full rounded-xl border border-outline-variant/40 bg-surface p-3 hover:bg-surface-container-low'
              }
            >
              <button
                type="button"
                onClick={() => onOpenConversation(entry.conversationId)}
                className="w-full text-left"
              >
                <p className="text-sm font-semibold text-primary truncate">{entry.title}</p>
                <p className="text-xs text-on-surface-variant mt-1 truncate">{entry.lastAgent || 'Agent unknown'}</p>
                <p className="text-[11px] text-on-surface-variant mt-1">{new Date(entry.updatedAt).toLocaleString()}</p>
              </button>
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => onDeleteConversation(entry.conversationId)}
                  className="text-[11px] font-semibold text-error border border-error/40 px-2 py-1 rounded-lg bg-error/10"
                >
                  Delete
                </button>
              </div>
            </div>
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
  );
}
