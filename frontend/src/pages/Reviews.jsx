import React from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, ListPage } from "../components.jsx";

export default function Reviews() {
  const { data: enums } = useApi("/meta/enums");
  const e = enums || {};
  const yesNo = [{ value: "true", label: "Yes" }, { value: "false", label: "No" }];
  const fields = [
    { name: "q", label: "Search review, customer", type: "text" },
    { name: "status", label: "Status", type: "select", options: e.review_status },
    { name: "overdue", label: "Overdue", type: "select", options: yesNo },
    { name: "closed_without_resolution", label: "Closed without resolution", type: "select", options: yesNo },
    { name: "risk_level", label: "Risk level", type: "select", options: e.risk_level },
    { name: "due_from", label: "Due from", type: "date" },
    { name: "due_to", label: "Due to", type: "date" },
    { name: "sort", label: "Sort by", type: "select", options: ["due_date", "review_id", "closed_at", "opened_at"] },
    { name: "order", label: "Order", type: "select", options: ["asc", "desc"] },
  ];
  const columns = [
    { label: "Review", key: "review_id" },
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_name}</Link> },
    { label: "Risk", render: (r) => <Badge value={r.risk_level} /> },
    { label: "Due", key: "due_date" },
    { label: "Status", render: (r) => <Badge value={r.status} /> },
    { label: "Days overdue", className: "num", render: (r) => (r.days_overdue ? <span className="over">{r.days_overdue}</span> : "–") },
    { label: "Opened", render: (r) => r.opened_at || "–" },
    { label: "Closed", render: (r) => r.closed_at || "–" },
    { label: "Resolution", className: "wrap", render: (r) => r.resolution || (r.status === "CLOSED" ? <span className="over">missing</span> : "–") },
    { label: "Closed by", render: (r) => r.closed_by || "–" },
  ];
  return (
    <ListPage title="Periodic reviews" subtitle="Review cadence depends on the customer's risk level. Overdue is calculated from the due date."
      path="/reviews" defaults={{ q: "", status: "", overdue: "", closed_without_resolution: "", risk_level: "", due_from: "", due_to: "", sort: "due_date", order: "asc" }}
      fields={fields} columns={columns} />
  );
}
