import React from "react";
import { useApi } from "../hooks.js";
import { BarList, Card, ErrorBox, Loading, Stat, fmtNum } from "../components.jsx";

export default function Dashboard() {
  const { data: d, error, loading } = useApi("/dashboard/summary");
  if (error) return <ErrorBox error={error} />;
  if (loading || !d) return <Loading />;
  const ev = d.evaluation;
  const repro = d.reproducibility;
  return (
    <div>
      <h1>Dashboard</h1>
      <p className="muted">All figures are calculated live from the database as of {d.as_of_date}. Click any number or bar to see the records behind it.</p>

      <div className="stats">
        <Stat label="Customers" value={fmtNum(d.customers.total)} to="/customers" />
        <Stat label="Approved but evidence incomplete" value={fmtNum(d.completeness.approved_incomplete)}
          hint={`of ${fmtNum(d.completeness.approved_total)} approved`} bad={d.completeness.approved_incomplete > 0}
          to="/customers?status=APPROVED&completeness=INCOMPLETE" />
        <Stat label="Open alerts" value={fmtNum(d.alerts.open)} to="/alerts?status=OPEN" />
        <Stat label="Overdue reviews" value={fmtNum(d.reviews.overdue)} bad={d.reviews.overdue > 0} to="/reviews?overdue=true" />
        <Stat label="Documents expiring in 30 days" value={fmtNum(d.documents.verified_expiring_within_days["30"])} to="/documents?expiring_within_days=30" />
        <Stat label="Exceptions raised" value={fmtNum(d.exceptions.total)} hint={`${fmtNum(d.exceptions.open)} open`} bad={d.exceptions.open > 0} to="/exceptions" />
      </div>

      <div className="grid g2">
        <Card title="Customers by status"><BarList data={d.customers.by_status} linkFor={(k) => `/customers?status=${k}`} /></Card>
        <Card title="Customers by risk level"><BarList data={d.customers.by_risk_level} linkFor={(k) => `/customers?risk_level=${k}`} /></Card>
        <Card title="Evidence completeness"><BarList data={d.completeness.by_label} linkFor={(k) => `/customers?completeness=${k}`} /></Card>
        <Card title="Documents by calculated state"><BarList data={d.documents.by_state} linkFor={(k) => `/documents?state=${k}`} /></Card>
        <Card title="Verified documents expiring within…">
          <BarList data={{ "30 days": d.documents.verified_expiring_within_days["30"], "60 days": d.documents.verified_expiring_within_days["60"], "90 days": d.documents.verified_expiring_within_days["90"] }} />
        </Card>
        <Card title="Reviews by status"><BarList data={d.reviews.by_status} linkFor={(k) => `/reviews?status=${k}`} /></Card>
        <Card title="Alerts by severity"><BarList data={d.alerts.by_severity} linkFor={(k) => `/alerts?severity=${k}`} /></Card>
        <Card title="Exceptions by rule"><BarList data={d.exceptions.by_type} linkFor={(k) => `/exceptions?issue_type=${k}`} /></Card>
      </div>

      <div className="grid g2">
        <Card title="Detection quality (against labelled ground truth)">
          {ev ? (
            <>
              <div className="stats">
                <Stat label="Precision" value={ev.precision} />
                <Stat label="Recall" value={ev.recall} />
                <Stat label="F1" value={ev.f1} />
              </div>
              <p className="muted small">True positives {ev.true_positives}, false positives {ev.false_positives}, false negatives {ev.false_negatives}.
                These scores measure agreement between the rules and the injected labels on this synthetic data; they are not a claim about real-world data.</p>
            </>
          ) : <p className="muted">Ground truth file not found. Run <code>python -m generator.generate</code>.</p>}
        </Card>
        <Card title="Reproducibility">
          {repro ? (
            <dl className="kv">
              <dt>Seed</dt><dd>{repro.seed}</dd>
              <dt>Final database SHA-256</dt><dd className="mono hash">{repro.final_database_sha256}</dd>
              <dt>Clean baseline SHA-256</dt><dd className="mono hash">{repro.baseline_database_sha256}</dd>
            </dl>
          ) : <p className="muted">Validation report not found. Run <code>python -m generator.generate</code>.</p>}
        </Card>
      </div>
    </div>
  );
}
