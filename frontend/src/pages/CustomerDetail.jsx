import React from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, Card, CompletenessBar, DataTable, ErrorBox, Loading, fmtNum, shortHash } from "../components.jsx";

export default function CustomerDetail() {
  const { id } = useParams();
  const { data: c, error, loading } = useApi(`/customers/${id}`);
  if (error) return <ErrorBox error={error} />;
  if (loading || !c) return <Loading />;
  const comp = c.completeness;
  return (
    <div>
      <p className="small"><Link to="/customers">← Customers</Link></p>
      <h1>{c.full_name} <span className="muted small">{c.customer_id}</span></h1>
      <div className="grid g2">
        <Card title="Profile">
          <dl className="kv">
            <dt>Type</dt><dd>{c.customer_type_name}</dd>
            <dt>Status</dt><dd><Badge value={c.status} /></dd>
            <dt>Risk</dt><dd><Badge value={c.risk_level} /> {c.risk_score !== null && <span className="muted small">score {c.risk_score}</span>}</dd>
            <dt>Country</dt><dd>{c.country_code}</dd>
            <dt>Email</dt><dd>{c.email || "–"}</dd>
            <dt>Date of birth</dt><dd>{c.date_of_birth || "–"}</dd>
            <dt>Created</dt><dd>{c.created_at}</dd>
            <dt>Onboarded</dt><dd>{c.onboarded_at || "–"}</dd>
            <dt>Next review due</dt><dd>{c.next_review_due || "–"}</dd>
            {c.business_profile && (<>
              <dt>Registration no.</dt><dd>{c.business_profile.registration_number}</dd>
              <dt>Incorporated</dt><dd>{c.business_profile.incorporation_date} ({c.business_profile.country_of_incorporation})</dd>
            </>)}
          </dl>
          <p className="small"><Link to={`/audit?entity_id=${c.customer_id}`}>View audit trail →</Link></p>
        </Card>
        <Card title="Evidence completeness" right={<Badge value={comp.label} />}>
          <CompletenessBar percent={comp.percent} label={comp.label} />
          <p className="small muted">{comp.satisfied} of {comp.required} mandatory requirements satisfied.</p>
          {comp.missing.length === 0 ? <p>Nothing missing.</p> : (
            <ul className="clean">
              {comp.missing.map((m) => (
                <li key={m.requirement_id}><Badge value={m.state} /> <strong>{m.name}</strong> <span className="muted small">– {m.reason}</span></li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title={`Documents (${c.documents.length})`}>
        <DataTable rows={c.documents} columns={[
          { label: "Document", key: "document_id" },
          { label: "File", key: "file_name" },
          { label: "Satisfies", render: (r) => r.requirement_ids.join(", ") || "–" },
          { label: "Issued", key: "issue_date" },
          { label: "Expires", render: (r) => r.expiry_date || "–" },
          { label: "Days left", className: "num", render: (r) => (r.days_to_expiry === null ? "–" : <span className={r.days_to_expiry < 0 ? "over" : ""}>{fmtNum(r.days_to_expiry)}</span>) },
          { label: "Stored status", render: (r) => <Badge value={r.status} /> },
          { label: "Calculated state", render: (r) => <Badge value={r.effective_state} /> },
          { label: "Hash", render: (r) => <Link to={`/documents?file_hash=${r.file_hash}`} className="mono">{shortHash(r.file_hash)}</Link> },
        ]} />
      </Card>

      <div className="grid g2">
        <Card title="Risk history">
          <DataTable rows={c.risk_history} columns={[
            { label: "Level", render: (r) => <Badge value={r.level} /> }, { label: "Score", key: "score" },
            { label: "From", key: "effective_from" }, { label: "To", render: (r) => r.effective_to || "current" },
            { label: "Reason", key: "reason", className: "wrap" },
          ]} />
        </Card>
        <Card title="Review cases">
          <DataTable rows={c.reviews} empty="No review cases." columns={[
            { label: "Review", key: "review_id" }, { label: "Due", key: "due_date" },
            { label: "Status", render: (r) => <Badge value={r.status} /> }, { label: "Resolution", render: (r) => r.resolution || "–", className: "wrap" },
          ]} />
        </Card>
      </div>

      <Card title="Alerts">
        <DataTable rows={c.alerts} empty="No alerts." columns={[
          { label: "Alert", key: "alert_id" }, { label: "Type", render: (r) => <Badge value={r.alert_type} /> },
          { label: "Severity", render: (r) => <Badge value={r.severity} /> }, { label: "Status", render: (r) => <Badge value={r.status} /> },
          { label: "Message", key: "message", className: "wrap" }, { label: "Raised", key: "created_at" },
        ]} />
      </Card>

      {c.ownership.length > 0 && (
        <Card title="Beneficial ownership" right={<span className={c.ownership_active_total > 100 ? "over" : ""}>Active total: {c.ownership_active_total}%</span>}>
          <DataTable rows={c.ownership} columns={[
            { label: "Owner", key: "owner_name" }, { label: "Share %", className: "num", render: (r) => r.ownership_pct },
            { label: "From", key: "effective_from" }, { label: "To", render: (r) => r.effective_to || "–" },
            { label: "Active", render: (r) => <Badge value={r.active ? "VALID" : "IGNORED"} /> },
          ]} />
        </Card>
      )}
    </div>
  );
}
