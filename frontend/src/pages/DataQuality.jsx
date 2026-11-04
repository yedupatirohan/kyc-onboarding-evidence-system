import React from "react";
import { useApi } from "../hooks.js";
import { Badge, Card, DataTable, ErrorBox, Loading, Stat, fmtNum } from "../components.jsx";

export default function DataQuality() {
  const checks = useApi("/validation");
  const report = useApi("/validation/report");
  const counts = useApi("/validation/row-counts");
  return (
    <div>
      <h1>Data quality</h1>
      <p className="muted">Twelve automated checks run against the live database. The clean-baseline proof shows the data had zero violations before anomalies were injected.</p>

      <Card title="Clean baseline (before any anomaly was injected)">
        {report.error && <ErrorBox error={report.error} />}
        {report.loading && <Loading />}
        {report.data && (
          <>
            <div className="stats">
              <Stat label="Baseline clean" value={report.data.baseline.clean ? "Yes" : "No"} bad={!report.data.baseline.clean} />
              <Stat label="Checks with violations" value={report.data.baseline.checks_with_violations} />
              <Stat label="Anomaly findings" value={report.data.baseline.anomaly_findings} />
              <Stat label="Seed" value={report.data.seed} />
            </div>
            <dl className="kv">
              <dt>Baseline SHA-256</dt><dd className="mono hash">{report.data.reproducibility_checksums.baseline_overall}</dd>
              <dt>Final SHA-256</dt><dd className="mono hash">{report.data.reproducibility_checksums.final_overall}</dd>
              {Object.entries(report.data.environment || {}).map(([k, v]) => (<React.Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd>{String(v)}</dd></React.Fragment>))}
            </dl>
          </>
        )}
      </Card>

      <Card title="Validation checks (live, after injection)">
        {checks.error && <ErrorBox error={checks.error} />}
        {checks.loading && <Loading />}
        {checks.data && (
          <>
            <p className="muted small">{checks.data.passing} of {checks.data.total} pass. {checks.data.note}</p>
            <DataTable rows={checks.data.checks.map((c) => ({ id: c.name, ...c }))} columns={[
              { label: "Check", key: "name" },
              { label: "Result", render: (r) => <Badge value={r.passed ? "PASS" : "FAIL"} /> },
              { label: "Violations", key: "violations", className: "num" },
              { label: "What it verifies", key: "description", className: "wrap" },
              { label: "Examples", className: "wrap", render: (r) => (r.samples.length ? r.samples.join("; ") : "–") },
            ]} />
          </>
        )}
      </Card>

      <Card title="Rows per table (14 tables)">
        {counts.error && <ErrorBox error={counts.error} />}
        {counts.loading && <Loading />}
        {counts.data && (
          <DataTable rows={Object.entries(counts.data.counts).map(([table, n]) => ({ id: table, table, n }))} columns={[
            { label: "Table", key: "table" }, { label: "Rows", className: "num", render: (r) => fmtNum(r.n) },
          ]} />
        )}
      </Card>
    </div>
  );
}
