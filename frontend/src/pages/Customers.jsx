import React from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, CompletenessBar, ListPage } from "../components.jsx";

export default function Customers() {
  const { data: enums } = useApi("/meta/enums");
  const { data: types } = useApi("/meta/customer-types");
  const e = enums || {};
  const fields = [
    { name: "q", label: "Search name or ID", type: "text", placeholder: "e.g. CUS-000123" },
    { name: "status", label: "Status", type: "select", options: e.customer_status },
    { name: "risk_level", label: "Risk level", type: "select", options: e.risk_level },
    { name: "completeness", label: "Evidence completeness", type: "select", options: e.completeness_label },
    { name: "customer_type_id", label: "Customer type", type: "select", options: (types || []).map((t) => ({ value: t.customer_type_id, label: t.name })) },
    { name: "country_code", label: "Country (2 letters)", type: "text", placeholder: "IN" },
    { name: "sort", label: "Sort by", type: "select", options: ["customer_id", "full_name", "created_at", "onboarded_at", "risk_score"] },
    { name: "order", label: "Order", type: "select", options: ["asc", "desc"] },
  ];
  const columns = [
    { label: "Customer", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.customer_id}</Link> },
    { label: "Name", key: "full_name" },
    { label: "Type", key: "customer_type_id" },
    { label: "Country", key: "country_code" },
    { label: "Status", render: (r) => <Badge value={r.status} /> },
    { label: "Risk", render: (r) => <Badge value={r.risk_level} /> },
    { label: "Evidence", render: (r) => <CompletenessBar percent={r.completeness_percent} label={r.completeness_label} /> },
    { label: "Completeness", render: (r) => <Badge value={r.completeness_label} /> },
    { label: "Missing", key: "missing_count", className: "num" },
    { label: "Onboarded", render: (r) => r.onboarded_at || "–" },
  ];
  return (
    <ListPage title="Customers" subtitle="Evidence completeness is calculated from the KYC rules, not stored."
      path="/customers" defaults={{ q: "", status: "", risk_level: "", completeness: "", customer_type_id: "", country_code: "", sort: "customer_id", order: "asc" }}
      fields={fields} columns={columns} />
  );
}
