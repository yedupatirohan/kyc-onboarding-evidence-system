import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, Card, DataTable, ErrorBox, ListPage, Loading } from "../components.jsx";

const OUTCOMES = ["TRUE_POSITIVE", "FALSE_NEGATIVE", "CONTROL_WRONGLY_FLAGGED", "CONTROL_CORRECTLY_IGNORED", "UNLABELLED_FINDING"];

export default function Exceptions() {
  const [search] = useSearchParams();
  const startOnCompare = ["outcome", "label_kind", "detected"].some((k) => search.get(k) !== null);
  const [tab, setTab] = useState(startOnCompare ? "compare" : "raised");
  const summary = useApi("/exceptions/summary");
  const evaluation = useApi("/evaluation");
  const issueTypes = (summary.data || []).map((s) => s.issue_type);

  return (
    <div>
      <h1>Exceptions</h1>
      <p className="muted">Five mandatory rules find records that break KYC policy. Below, the same detectors are compared with the labelled ground truth.</p>

      <Card title="The five rules">
        {summary.error && <ErrorBox error={summary.error} />}
        {summary.loading && <Loading />}
        {summary.data && (
          <DataTable rows={summary.data} columns={[
            { label: "Rule", render: (r) => <Link to={`/exceptions?issue_type=${r.issue_type}`}><Badge value={r.issue_type} /></Link> },
            { label: "Severity", render: (r) => <Badge value={r.severity} /> },
            { label: "What it checks", key: "rule", className: "wrap" },
            { label: "Expected business decision", key: "expected_decision", className: "wrap" },
            { label: "Raised", key: "total", className: "num" },
            { label: "Open", key: "open", className: "num" },
            { label: "Acknowledged", key: "acknowledged", className: "num" },
            { label: "Resolved", key: "resolved", className: "num" },
          ]} />
        )}
      </Card>

      <Card title="Detection vs ground truth">
        {evaluation.error && <ErrorBox error={evaluation.error} />}
        {evaluation.loading && <Loading />}
        {evaluation.data && (
          <>
            <p className="muted small">Source: {evaluation.data.source.file} – {evaluation.data.source.injected_anomalies} injected anomalies and {evaluation.data.source.near_miss_controls} near-miss controls (valid records that look suspicious; a good detector must not flag them).
              Overall precision {evaluation.data.overall.precision}, recall {evaluation.data.overall.recall}, F1 {evaluation.data.overall.f1}.</p>
            <DataTable rows={Object.entries(evaluation.data.per_issue_type).map(([name, m]) => ({ id: name, name, ...m }))} columns={[
              { label: "Rule", render: (r) => <Badge value={r.name} /> },
              { label: "Labelled", key: "labelled_anomalies", className: "num" },
              { label: "Detected", key: "detected", className: "num" },
              { label: "TP", key: "true_positives", className: "num" },
              { label: "FP", key: "false_positives", className: "num" },
              { label: "FN", key: "false_negatives", className: "num" },
              { label: "Precision", key: "precision", className: "num" },
              { label: "Recall", key: "recall", className: "num" },
              { label: "Controls wrongly flagged", render: (r) => `${r.controls_wrongly_flagged} of ${r.near_miss_controls}`, className: "num" },
            ]} />
          </>
        )}
      </Card>

      <div className="tabs">
        <button className={`tab ${tab === "raised" ? "on" : ""}`} onClick={() => setTab("raised")}>Raised exceptions</button>
        <button className={`tab ${tab === "compare" ? "on" : ""}`} onClick={() => setTab("compare")}>Ground-truth comparison</button>
      </div>
      {tab === "raised" ? <Raised issueTypes={issueTypes} /> : <Compare issueTypes={issueTypes} />}
    </div>
  );
}

function Raised({ issueTypes }) {
  const { data: enums } = useApi("/meta/enums");
  const e = enums || {};
  const fields = [
    { name: "q", label: "Search id, message, customer", type: "text" },
    { name: "issue_type", label: "Rule", type: "select", options: issueTypes },
    { name: "severity", label: "Severity", type: "select", options: e.alert_severity },
    { name: "status", label: "Status", type: "select", options: e.alert_status },
  ];
  const columns = [
    { label: "Alert", key: "alert_id" },
    { label: "Rule", render: (r) => <Badge value={r.alert_type} /> },
    { label: "Severity", render: (r) => <Badge value={r.severity} /> },
    { label: "Status", render: (r) => <Badge value={r.status} /> },
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_name}</Link> },
    { label: "Document", render: (r) => r.document_id || "–" },
    { label: "Why it was raised", key: "message", className: "wrap" },
    { label: "Expected decision", key: "expected_decision", className: "wrap" },
  ];
  return <ListPage title="Raised exceptions" path="/exceptions" defaults={{ q: "", issue_type: "", severity: "", status: "" }} fields={fields} columns={columns} />;
}

function Compare({ issueTypes }) {
  const fields = [
    { name: "q", label: "Search entity id", type: "text" },
    { name: "issue_type", label: "Rule", type: "select", options: issueTypes },
    { name: "outcome", label: "Outcome", type: "select", options: OUTCOMES },
    { name: "label_kind", label: "Label", type: "select", options: ["injected_anomaly", "near_miss_control"] },
    { name: "detected", label: "Detected by rules", type: "select", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
  ];
  const columns = [
    { label: "Label ID", render: (r) => r.ground_truth_id || "–" },
    { label: "Rule", render: (r) => <Badge value={r.issue_type} /> },
    { label: "Record", render: (r) => `${r.entity_type} ${r.entity_id}` },
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_id}</Link> },
    { label: "Label", render: (r) => (r.label_kind ? r.label_kind.replaceAll("_", " ") : "none") },
    { label: "Detected", render: (r) => <Badge value={r.detected ? "TRUE_POSITIVE" : "IGNORED"} /> },
    { label: "Outcome", render: (r) => <Badge value={r.outcome} /> },
    { label: "Injected change", key: "injected_change", className: "wrap" },
    { label: "Detector reason", key: "reason", className: "wrap" },
  ];
  return <ListPage title="Ground-truth comparison" subtitle="True positive = injected and found. Control correctly ignored = looks suspicious but valid, and was not flagged."
    path="/anomalies" defaults={{ q: "", issue_type: "", outcome: "", label_kind: "", detected: "" }} fields={fields} columns={columns} />;
}
