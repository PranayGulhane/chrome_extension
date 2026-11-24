import { useEffect, useMemo, useState } from "react";
import type {
  ArchiveMailRowResponse,
  ContentToBackgroundMessage,
  DraftFollowupResponse,
  GetSentMailPageResponse,
  GmailConnectResponse,
  GmailDisconnectResponse,
  GmailStatus,
  GmailStatusResponse,
  MailboxSummary,
  SendFollowupResponse,
  SentMailRow,
  UnarchiveMailRowResponse,
} from "../shared/types";

type PageState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; rows: SentMailRow[]; summary: MailboxSummary; nextPageToken: string | null }
  | { kind: "error"; message: string };

type SortKey = "sent_at" | "last_followup_at" | "subject" | "recipient";
type PageSize = 10 | 20 | 50 | 100;

const PAGE_SIZE_OPTIONS: PageSize[] = [10, 20, 50, 100];

export function ManageGmailView() {
  const [pageSize, setPageSize] = useState<PageSize>(20);
  // Gmail only gives a forward pageToken — "Previous" is a client-side stack of tokens we've
  // already seen, popped to go back. Current page's token is always the stack's last entry.
  const [pageTokenStack, setPageTokenStack] = useState<(string | null)[]>([null]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [pageState, setPageState] = useState<PageState>({ kind: "idle" });

  const [sourceFilter, setSourceFilter] = useState<"all" | "platform" | "external">("all");
  const [replyFilter, setReplyFilter] = useState<"all" | "awaiting" | "replied">("all");
  const [searchText, setSearchText] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("sent_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const [openRow, setOpenRow] = useState<SentMailRow | null>(null);

  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  async function refreshGmailStatus() {
    setAccountError(null);
    const message: ContentToBackgroundMessage = { type: "GMAIL_STATUS" };
    const response = (await chrome.runtime.sendMessage(message)) as GmailStatusResponse;
    if (response.ok) {
      setGmailStatus(response.status);
    } else {
      setAccountError(response.error);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setAccountError(null);
    const message: ContentToBackgroundMessage = { type: "GMAIL_CONNECT" };
    const response = (await chrome.runtime.sendMessage(message)) as GmailConnectResponse;
    setConnecting(false);
    if (!response.ok) setAccountError(response.error);
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setAccountError(null);
    const message: ContentToBackgroundMessage = { type: "GMAIL_DISCONNECT" };
    const response = (await chrome.runtime.sendMessage(message)) as GmailDisconnectResponse;
    setDisconnecting(false);
    if (!response.ok) {
      setAccountError(response.error);
      return;
    }
    await refreshGmailStatus();
  }

  useEffect(() => {
    void refreshGmailStatus();
  }, []);

  async function fetchPage(token: string | null) {
    setPageState({ kind: "loading" });
    const message: ContentToBackgroundMessage = {
      type: "GET_SENT_MAIL_PAGE",
      pageSize,
      pageToken: token ?? undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    };
    const response = (await chrome.runtime.sendMessage(message)) as GetSentMailPageResponse;
    if (!response.ok) {
      setPageState({ kind: "error", message: response.error });
      return;
    }
    setPageState({ kind: "loaded", rows: response.rows, summary: response.summary, nextPageToken: response.nextPageToken });
  }

  // Also covers the initial mount (an effect with a dependency array runs on mount too, not just
  // on subsequent changes) — a separate mount-only effect calling fetchPage(null) here as well
  // used to fire a second, concurrent GET_SENT_MAIL_PAGE request on first render, racing this one
  // to insert the same Gmail messages and crashing on gmail_sent_messages' unique constraint.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    setPageTokenStack([null]);
    void fetchPage(null);
  }, [pageSize]);

  function handleApplyDateFilter() {
    setPageTokenStack([null]);
    void fetchPage(null);
  }

  function handleNext() {
    if (pageState.kind !== "loaded" || !pageState.nextPageToken) return;
    const next = pageState.nextPageToken;
    setPageTokenStack((prev) => [...prev, next]);
    void fetchPage(next);
  }

  function handlePrevious() {
    if (pageTokenStack.length <= 1) return;
    const newStack = pageTokenStack.slice(0, -1);
    setPageTokenStack(newStack);
    void fetchPage(newStack[newStack.length - 1] ?? null);
  }

  function handleRowUpdated(updated: SentMailRow) {
    setPageState((prev) =>
      prev.kind === "loaded" ? { ...prev, rows: prev.rows.map((r) => (r.id === updated.id ? updated : r)) } : prev,
    );
    setOpenRow((prev) => (prev && prev.id === updated.id ? updated : prev));
  }

  const visibleRows = useMemo(() => {
    if (pageState.kind !== "loaded") return [];
    let rows = pageState.rows;
    if (!includeArchived) rows = rows.filter((r) => !r.is_archived);
    if (sourceFilter !== "all") rows = rows.filter((r) => r.source === sourceFilter);
    if (replyFilter !== "all") rows = rows.filter((r) => r.reply_status === replyFilter);
    if (searchText.trim()) {
      const needle = searchText.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          (r.subject ?? "").toLowerCase().includes(needle) ||
          (r.recipient ?? "").toLowerCase().includes(needle) ||
          (r.poster_name ?? "").toLowerCase().includes(needle) ||
          (r.company ?? "").toLowerCase().includes(needle),
      );
    }
    const sorted = [...rows].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      if (av === bv) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return av < bv ? -1 : 1;
    });
    if (sortDir === "desc") sorted.reverse();
    return sorted;
  }, [pageState, includeArchived, sourceFilter, replyFilter, searchText, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div>
      <div className="field" style={{ marginBottom: 14 }}>
        <label>Gmail account</label>
        {accountError && <p className="error-text">{accountError}</p>}

        {gmailStatus && !gmailStatus.connected && (
          <>
            <p className="notice-text">Not connected — connect your Gmail account to send and track email.</p>
            <button className="btn-secondary" onClick={handleConnect} disabled={connecting}>
              {connecting ? "Opening…" : "Connect Gmail"}
            </button>
            <button className="btn-secondary" onClick={refreshGmailStatus} style={{ marginLeft: 8 }}>
              I&apos;ve connected — refresh
            </button>
          </>
        )}

        {gmailStatus && gmailStatus.connected && (
          <>
            <p className="muted">Connected as {gmailStatus.gmail_address}</p>
            <button className="btn-secondary" onClick={handleDisconnect} disabled={disconnecting}>
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </button>
          </>
        )}
      </div>

      <p className="muted" style={{ marginBottom: 10 }}>
        Every email you&apos;ve sent, newest first — flagged Platform (sent through this extension) or External.
        Draft and send a follow-up in the same thread, or archive a row to stop follow-up suggestions on it.
      </p>

      <div className="control-row">
        <div className="field">
          <label>From (optional)</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="field">
          <label>To (optional)</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <button className="btn-secondary" onClick={handleApplyDateFilter}>
          Apply
        </button>
      </div>

      {pageState.kind === "error" && <p className="error-text">{pageState.message}</p>}
      {pageState.kind === "loading" && <p className="muted">Loading…</p>}

      {pageState.kind === "loaded" && (
        <>
          <MailboxSummaryStrip summary={pageState.summary} hasDateFilter={Boolean(dateFrom || dateTo)} />

          <div className="control-row">
            <div className="field">
              <label>Source</label>
              <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as typeof sourceFilter)}>
                <option value="all">All</option>
                <option value="platform">Platform</option>
                <option value="external">External</option>
              </select>
            </div>
            <div className="field">
              <label>Reply status</label>
              <select value={replyFilter} onChange={(e) => setReplyFilter(e.target.value as typeof replyFilter)}>
                <option value="all">All</option>
                <option value="awaiting">Awaiting</option>
                <option value="replied">Replied</option>
              </select>
            </div>
            <div className="field" style={{ flex: 2 }}>
              <label>Search</label>
              <input
                type="text"
                placeholder="Subject, recipient…"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, fontSize: 13 }}>
            <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
            Include archived
          </label>
          <p className="filter-note">Filters apply to the current page only — they don&apos;t fetch more pages.</p>

          {visibleRows.length === 0 && <p className="muted">No sent mail matches these filters on this page.</p>}

          {visibleRows.length > 0 && (
            <div className="mail-table-wrap">
              <table className="mail-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th onClick={() => handleSort("recipient")} className={sortKey === "recipient" ? "sorted" : undefined}>
                      Recipient
                    </th>
                    <th onClick={() => handleSort("subject")} className={sortKey === "subject" ? "sorted" : undefined}>
                      Subject
                    </th>
                    <th onClick={() => handleSort("sent_at")} className={sortKey === "sent_at" ? "sorted" : undefined}>
                      Sent
                    </th>
                    <th
                      onClick={() => handleSort("last_followup_at")}
                      className={sortKey === "last_followup_at" ? "sorted" : undefined}
                    >
                      Last follow-up
                    </th>
                    <th>Reply</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <MailRow key={row.id} row={row} onOpenFollowup={() => setOpenRow(row)} onUpdated={handleRowUpdated} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="pagination-row">
            <button className="btn-secondary" onClick={handlePrevious} disabled={pageTokenStack.length <= 1}>
              ← Previous
            </button>
            <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value) as PageSize)}>
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size} / page
                </option>
              ))}
            </select>
            <button className="btn-secondary" onClick={handleNext} disabled={!pageState.nextPageToken}>
              Next →
            </button>
          </div>
        </>
      )}

      {openRow && (
        <FollowupModal row={openRow} onClose={() => setOpenRow(null)} onSent={handleRowUpdated} />
      )}
    </div>
  );
}

function sortValue(row: SentMailRow, key: SortKey): string | null {
  switch (key) {
    case "sent_at":
      return row.sent_at;
    case "last_followup_at":
      return row.last_followup_at;
    case "subject":
      return row.subject;
    case "recipient":
      return row.recipient;
  }
}

function MailboxSummaryStrip({ summary, hasDateFilter }: { summary: MailboxSummary; hasDateFilter: boolean }) {
  const pct = (rate: number | null) => (rate !== null ? `${Math.round(rate * 100)}%` : "—");
  return (
    <div style={{ marginBottom: 4 }}>
      <p className="muted" style={{ marginBottom: 6 }}>
        {hasDateFilter
          // The gmail.metadata scope this app uses can't filter by date server-side (see
          // gmail_service.list_sent_messages_page), so the date filter is applied after fetching —
          // Gmail's own estimate below is for the whole Sent mailbox, not the filtered range.
          ? `~${summary.result_size_estimate ?? "?"} sent overall (unfiltered) · figures below are from what's been loaded and matches your date filter so far`
          : `~${summary.result_size_estimate ?? "?"} sent · figures below are from what's been loaded so far`}
      </p>
      <div className="field-grid">
        <div className="field-grid-item">
          <label>Loaded</label>
          <div>{summary.loaded_count}</div>
        </div>
        <div className="field-grid-item">
          <label>Via platform</label>
          <div>{summary.sent_via_platform}</div>
        </div>
        <div className="field-grid-item">
          <label>Follow-ups sent</label>
          <div>{summary.followups_sent}</div>
        </div>
        <div className="field-grid-item">
          <label>Replies</label>
          <div>
            {summary.replies_detected} ({pct(summary.response_rate)})
          </div>
        </div>
        <div className="field-grid-item">
          <label>Awaiting response</label>
          <div>{summary.awaiting_response}</div>
        </div>
      </div>
    </div>
  );
}

function MailRow({
  row,
  onOpenFollowup,
  onUpdated,
}: {
  row: SentMailRow;
  onOpenFollowup: () => void;
  onUpdated: (row: SentMailRow) => void;
}) {
  const [archiving, setArchiving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggleArchive() {
    setArchiving(true);
    setError(null);
    const message: ContentToBackgroundMessage = row.is_archived
      ? { type: "UNARCHIVE_MAIL_ROW", gmailSentMessageId: row.id }
      : { type: "ARCHIVE_MAIL_ROW", gmailSentMessageId: row.id };
    const response = (await chrome.runtime.sendMessage(message)) as ArchiveMailRowResponse | UnarchiveMailRowResponse;
    setArchiving(false);
    if (!response.ok) {
      setError(response.error);
      return;
    }
    onUpdated(response.row);
  }

  return (
    <>
      <tr style={row.is_archived ? { opacity: 0.6 } : undefined}>
        <td>
          <span className={`tag ${row.source === "platform" ? "tag-platform" : "tag-external"}`}>
            {row.source === "platform" ? "Platform" : "External"}
          </span>
          {row.source === "platform" && (row.poster_name || row.company) && (
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              {row.poster_name}
              {row.company ? ` · ${row.company}` : ""}
            </div>
          )}
        </td>
        <td>{row.recipient ?? "—"}</td>
        <td>{row.subject ?? "—"}</td>
        <td>{row.sent_at ? new Date(row.sent_at).toLocaleDateString() : "—"}</td>
        <td>{row.last_followup_at ? new Date(row.last_followup_at).toLocaleDateString() : "—"}</td>
        <td>
          <span className={`tag ${row.reply_status === "replied" ? "tag-match" : "tag-outreach"}`}>
            {row.reply_status === "replied" ? "Replied" : "Awaiting"}
          </span>
        </td>
        <td className="actions-cell">
          <button onClick={onOpenFollowup}>Follow up</button>
          <button onClick={handleToggleArchive} disabled={archiving}>
            {archiving ? "…" : row.is_archived ? "Unarchive" : "Archive"}
          </button>
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={7}>
            <p className="error-text" style={{ margin: "4px 0" }}>
              {error}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

type DraftState =
  | { kind: "loading" }
  | { kind: "ready"; grounding: "full" | "subject_only" }
  | { kind: "error"; message: string };

function FollowupModal({
  row,
  onClose,
  onSent,
}: {
  row: SentMailRow;
  onClose: () => void;
  onSent: (row: SentMailRow) => void;
}) {
  const [draft, setDraft] = useState<DraftState>({ kind: "loading" });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    const message: ContentToBackgroundMessage = { type: "DRAFT_FOLLOWUP", gmailSentMessageId: row.id };
    chrome.runtime.sendMessage(message).then((response: DraftFollowupResponse) => {
      if (!response.ok) {
        setDraft({ kind: "error", message: response.error });
        return;
      }
      setDraft({ kind: "ready", grounding: response.grounding });
      setSubject(response.subject);
      setBody(response.body);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.id]);

  async function handleSend() {
    setSending(true);
    setSendError(null);
    const message: ContentToBackgroundMessage = {
      type: "SEND_FOLLOWUP",
      gmailSentMessageId: row.id,
      subject,
      body,
    };
    const response = (await chrome.runtime.sendMessage(message)) as SendFollowupResponse;
    setSending(false);
    if (!response.ok) {
      setSendError(response.error);
      return;
    }
    onSent(response.row);
    onClose();
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-card-header">
          <h3>Follow up{row.subject ? `: ${row.subject}` : ""}</h3>
          <button onClick={onClose}>×</button>
        </div>

        {draft.kind === "loading" && <p className="muted">Drafting…</p>}
        {draft.kind === "error" && <p className="error-text">{draft.message}</p>}

        {draft.kind === "ready" && (
          <div className="field">
            {draft.grounding === "subject_only" && (
              <p className="notice-text">
                This email wasn&apos;t sent through this platform, so the draft below is based on the subject line
                only — review it carefully before sending.
              </p>
            )}
            <label>Subject</label>
            <input type="text" value={subject} onChange={(e) => setSubject(e.target.value)} />
            <label style={{ marginTop: 8 }}>Body</label>
            <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
            {sendError && <p className="error-text">{sendError}</p>}
            <button className="btn-primary" onClick={handleSend} disabled={sending} style={{ marginTop: 8 }}>
              {sending ? "Sending…" : "Send"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
