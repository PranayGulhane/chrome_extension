import { useEffect, useState } from "react";
import type { AgentTokenBreakdown, ContentToBackgroundMessage, GetMetricsResponse, UserMetrics } from "../shared/types";

function TokenBreakdownList({ breakdown }: { breakdown: AgentTokenBreakdown[] }) {
  if (breakdown.length === 0) return <p className="muted">No agent calls yet.</p>;
  return (
    <div>
      {breakdown.map((b) => (
        <div key={b.agent_name} className="muted">
          {b.agent_name}: {b.input_tokens} in / {b.output_tokens} out
        </div>
      ))}
    </div>
  );
}

export function UsageView() {
  const [metrics, setMetrics] = useState<UserMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const message: ContentToBackgroundMessage = { type: "GET_METRICS" };
    chrome.runtime.sendMessage(message).then((response: GetMetricsResponse) => {
      if (response.ok) {
        setMetrics(response.metrics);
      } else {
        setError(response.error);
      }
    });
  }, []);

  if (error) return <p className="error-text">{error}</p>;
  if (metrics === null) return <p className="muted">Loading…</p>;

  return (
    <div>
      <div className="field-grid">
        <div className="field-grid-item">
          <label>Total applications</label>
          <div>{metrics.total_applications}</div>
        </div>
        <div className="field-grid-item">
          <label>This month</label>
          <div>{metrics.total_applications_this_month}</div>
        </div>
        <div className="field-grid-item">
          <label>Emails sent</label>
          <div>{metrics.emails_sent}</div>
        </div>
        <div className="field-grid-item">
          <label>Drafted, not sent</label>
          <div>{metrics.drafted_not_sent}</div>
        </div>
      </div>

      <div className="field">
        <label>Most-used profile</label>
        <div>{metrics.most_used_profile ?? "—"}</div>
      </div>

      <div className="field">
        <label>Applications by status</label>
        {Object.keys(metrics.applications_by_status).length === 0 ? (
          <div className="muted">—</div>
        ) : (
          Object.entries(metrics.applications_by_status).map(([status, count]) => (
            <div key={status} className="muted">
              {status.replace(/_/g, " ")}: {count}
            </div>
          ))
        )}
      </div>

      <div className="field">
        <label>Tokens today</label>
        <TokenBreakdownList breakdown={metrics.tokens_today} />
      </div>

      <div className="field">
        <label>Tokens this month</label>
        <TokenBreakdownList breakdown={metrics.tokens_this_month} />
      </div>
    </div>
  );
}
