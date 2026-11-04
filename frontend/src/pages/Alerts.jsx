import React from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, ListPage } from "../components.jsx";

export default function Alerts() {
  const { data: enums } = useApi("/meta/enums");
  const e = enums || {};
  const fields = [
    { name: "q", label: "Search id, message, customer", type: "text" },
    { name: "alert_type", label: "Type", type: "select", options: e.alert_type },
    { name: "severity", label: "Severity", type: "select", options: e.alert_severity },
    { name: "status", label: "Status", type: "select", options: e.alert_status },
    { name: "lead_days", label: "Expiry warning", type: "select", options: [{ value: "90", label: "90-day" }, { value: "60", label: "60-day" }, { value: "30", label: "30-day" }] },
    { name: "created_from", label: "Raised from", type: "date" },
    { name: "created_to", label: "Raised to", type: "date" },
    { name: "sort", label: "Sort by", type: "select", options: ["created_at", "severity", "alert_id"] },
    { name: "order", label: "Order", type: "select", options: ["desc", "asc"] },
  ];
  const columns = [
    { label: "Alert", key: "alert_id" },
    { label: "Type", render: (r) => <Badge value={r.alert_type} /> },
    { label: "Severity", render: (r) => <Badge value={r.severity} /> },
    { label: "Status", render: (r) => <Badge value={r.status} /> },
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_name}</Link> },
    { label: "Document", render: (r) => r.document_id || "–" },
    { label: "Lead (days)", className: "num", render: (r) => (r.lead_days === null ? "–" : r.lead_days) },
    { label: "Message", key: "message", className: "wrap" },
    { label: "Raised", key: "created_at" },
  ];
  return (
    <ListPage title="Alerts" subtitle="Expiry warnings at 90/60/30 days, expired documents, and the five exception rules."
      path="/alerts" defaults={{ q: "", alert_type: "", severity: "", status: "", lead_days: "", created_from: "", created_to: "", sort: "created_at", order: "desc" }}
      fields={fields} columns={columns} />
  );
}
