import { useEffect, useState } from "react";
import * as metricsApi from "../api/metrics";
import type { AgentTokenBreakdown, UserMetricsResponse } from "../api/types";

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

export function MetricsPage() {
  const [metrics, setMetrics] = useState<UserMetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    metricsApi
      .getUserMetrics()
      .then(setMetrics)
      .catch(() => setError("Could not load your usage metrics."));
  }, []);

  return (
    <div className="page">
      <div className="section-title">
        <h2>Your usage</h2>
      </div>

      {error && <p className="error-text">{error}</p>}
      {metrics === null && !error && <p className="muted">Loading…</p>}

      {metrics && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="field-grid">
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  Total applications
                </div>
                <div>{metrics.total_applications}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  This month
                </div>
                <div>{metrics.total_applications_this_month}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  Emails sent
                </div>
                <div>{metrics.emails_sent}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  Drafted, not sent
                </div>
                <div>{metrics.drafted_not_sent}</div>
              </div>
            </div>
            <div style={{ marginTop: 14 }}>
              <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                Most-used profile
              </div>
              <div>{metrics.most_used_profile ?? "—"}</div>
            </div>
          </div>

          <h3 className="section-title">Applications by status</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {Object.keys(metrics.applications_by_status).length === 0 ? (
              <p className="muted">No applications yet.</p>
            ) : (
              Object.entries(metrics.applications_by_status).map(([status, count]) => (
                <div key={status}>
                  <span className="badge">{status.replace(/_/g, " ")}</span> {count}
                </div>
              ))
            )}
          </div>

          <h3 className="section-title">Tokens today</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            <TokenBreakdownList breakdown={metrics.tokens_today} />
          </div>

          <h3 className="section-title">Tokens this month</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            <TokenBreakdownList breakdown={metrics.tokens_this_month} />
          </div>
        </>
      )}
    </div>
  );
}
