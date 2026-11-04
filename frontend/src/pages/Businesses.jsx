import React from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks.js";
import { Badge, ListPage } from "../components.jsx";

export default function Businesses() {
  const { data: enums } = useApi("/meta/enums");
  const e = enums || {};
  const fields = [
    { name: "q", label: "Search name, ID or reg. no.", type: "text" },
    { name: "ownership_over_100", label: "Active ownership over 100%", type: "select", options: [{ value: "true", label: "Yes (problem)" }, { value: "false", label: "No" }] },
    { name: "risk_level", label: "Risk level", type: "select", options: e.risk_level },
    { name: "status", label: "Status", type: "select", options: e.customer_status },
    { name: "country_of_incorporation", label: "Incorporated in (2 letters)", type: "text" },
  ];
  const columns = [
    { label: "Business", render: (r) => <Link to={`/customers/${r.customer_id}`}>{r.full_name}</Link> },
    { label: "ID", key: "customer_id" },
    { label: "Type", key: "customer_type_id" },
    { label: "Reg. no.", key: "registration_number" },
    { label: "Incorporated", key: "incorporation_date" },
    { label: "Country", key: "country_of_incorporation" },
    { label: "Status", render: (r) => <Badge value={r.status} /> },
    { label: "Risk", render: (r) => <Badge value={r.risk_level} /> },
    { label: "Active owners", className: "num", key: "active_owner_count" },
    { label: "Active ownership %", className: "num", render: (r) => <span className={r.ownership_exceeds_100 ? "over" : ""}>{r.active_ownership_pct.toFixed(2)}</span> },
    { label: "Check", render: (r) => <Badge value={r.ownership_exceeds_100 ? "FAIL" : "PASS"} /> },
  ];
  return (
    <ListPage title="Businesses & beneficial ownership" subtitle="Active ownership shares of a business must not add up to more than 100%."
      path="/businesses" defaults={{ q: "", ownership_over_100: "", risk_level: "", status: "", country_of_incorporation: "" }}
      fields={fields} columns={columns} />
  );
}
