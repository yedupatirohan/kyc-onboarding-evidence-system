import React from "react";
import { useApi } from "../hooks.js";
import { Badge, ListPage } from "../components.jsx";

const preview = (v) => (v === null || v === undefined ? "–" : typeof v === "string" ? v : JSON.stringify(v));

export default function Audit() {
  const { data: facets } = useApi("/audit-events/facets");
  const f = facets || {};
  const fields = [
    { name: "entity_id", label: "Entity ID (exact)", type: "text", placeholder: "CUS-000001" },
    { name: "q", label: "Entity ID contains", type: "text" },
    { name: "entity_type", label: "Entity type", type: "select", options: f.entity_types },
    { name: "action", label: "Action", type: "select", options: f.actions },
    { name: "actor", label: "Actor", type: "select", options: f.actors },
    { name: "occurred_from", label: "From date", type: "date" },
    { name: "occurred_to", label: "To date", type: "date" },
    { name: "order", label: "Order", type: "select", options: ["desc", "asc"] },
  ];
  const columns = [
    { label: "When", render: (r) => r.occurred_at.replace("T", " ") },
    { label: "Entity", render: (r) => <span><Badge value={r.entity_type} /> <span className="mono">{r.entity_id}</span></span> },
    { label: "Action", render: (r) => r.action.replaceAll("_", " ") },
    { label: "Actor", key: "actor" },
    { label: "Before", render: (r) => <code className="jsonc" title={preview(r.old_value)}>{preview(r.old_value)}</code> },
    { label: "After", render: (r) => <code className="jsonc" title={preview(r.new_value)}>{preview(r.new_value)}</code> },
  ];
  return (
    <ListPage title="Audit trail" subtitle="Append-only history of status changes, verifications, reviews and alerts. Hover a before/after value to read it in full."
      path="/audit-events" defaults={{ entity_id: "", q: "", entity_type: "", action: "", actor: "", occurred_from: "", occurred_to: "", order: "desc" }}
      fields={fields} columns={columns} pageSize={30} />
  );
}
