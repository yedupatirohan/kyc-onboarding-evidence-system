import React from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, ListPage, fmtNum, shortHash } from "../components.jsx";

export default function Documents() {
  const { data: enums } = useApi("/meta/enums");
  const { data: reqs } = useApi("/meta/requirements");
  const e = enums || {};
  const fields = [
    { name: "q", label: "Search id, file or customer", type: "text" },
    { name: "state", label: "Calculated state", type: "select", options: e.document_state },
    { name: "status", label: "Stored status", type: "select", options: e.document_status },
    { name: "expiring_within_days", label: "Expiring within", type: "select", options: [{ value: "30", label: "30 days" }, { value: "60", label: "60 days" }, { value: "90", label: "90 days" }] },
    { name: "requirement_id", label: "Requirement", type: "select", options: (reqs || []).map((r) => ({ value: r.requirement_id, label: r.name })) },
    { name: "customer_id", label: "Customer ID", type: "text" },
    { name: "file_hash", label: "File hash (64 hex)", type: "text" },
    { name: "sort", label: "Sort by", type: "select", options: ["document_id", "submitted_at", "expiry_date", "issue_date"] },
    { name: "order", label: "Order", type: "select", options: ["asc", "desc"] },
  ];
  const columns = [
    { label: "Document", key: "document_id" },
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_name}</Link> },
    { label: "File", key: "file_name", className: "wrap" },
    { label: "Satisfies", render: (r) => r.requirement_ids.join(", ") || "–" },
    { label: "Issued", key: "issue_date" },
    { label: "Expires", render: (r) => r.expiry_date || "–" },
    { label: "Days left", className: "num", render: (r) => (r.days_to_expiry === null ? "–" : <span className={r.days_to_expiry < 0 ? "over" : ""}>{fmtNum(r.days_to_expiry)}</span>) },
    { label: "Stored", render: (r) => <Badge value={r.status} /> },
    { label: "Calculated", render: (r) => <Badge value={r.effective_state} /> },
    { label: "Hash", render: (r) => <Link to={`/documents?file_hash=${r.file_hash}`} className="mono" title="Show every document with this exact file">{shortHash(r.file_hash)}</Link> },
  ];
  return (
    <ListPage title="Documents" subtitle="Stored status is what the system recorded; calculated state applies the expiry rule to today's date. A mismatch is an exception."
      path="/documents" defaults={{ q: "", state: "", status: "", expiring_within_days: "", requirement_id: "", customer_id: "", file_hash: "", sort: "document_id", order: "asc" }}
      fields={fields} columns={columns} />
  );
}
