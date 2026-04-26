import { useState } from 'react';

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

export default function McpTurnCard({ turn, turnIndex }) {
  const [isExpanded, setIsExpanded] = useState(turn?.step_status === 'running');

  return (
    <div
      key={`mcp-turn-${turn.agent_id || 'agent'}-${turnIndex}`}
      className="mr-auto w-full max-w-[92%] rounded-2xl border border-secondary/40 bg-secondary/5 p-4"
    >
      <div
        className="flex items-center justify-between gap-2 mb-3 cursor-pointer"
        onClick={() => setIsExpanded((current) => !current)}
      >
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 rounded-md text-xs font-semibold bg-secondary text-white">MCP Activity</span>
          <span className="text-xs text-on-surface-variant">Live tool orchestration trace</span>
        </div>
        <button
          type="button"
          className="px-2 py-1 rounded-md text-xs font-semibold border border-outline-variant/50 bg-surface text-on-surface-variant"
          onClick={(event) => {
            event.stopPropagation();
            setIsExpanded((current) => !current);
          }}
        >
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {isExpanded && <div className="rounded-xl border border-outline-variant/40 bg-surface p-3">
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
      </div>}
    </div>
  );
}
