import React from "react";
import { Link } from "react-router-dom";
import { usePaged } from "./hooks.js";

export const fmtNum = (n) => (n === null || n === undefined ? "–" : Number(n).toLocaleString());
export const fmtPct = (n) => (n === null || n === undefined ? "–" : `${Number(n).toFixed(0)}%`);
export const shortHash = (h) => (h ? h.slice(0, 10) + "…" : "–");

export function tone(value) {
  const v = String(value || "").toUpperCase();
  if (["APPROVED", "VERIFIED", "VALID", "COMPLETE", "LOW", "RESOLVED", "CLOSED", "PASS", "TRUE_POSITIVE", "CONTROL_CORRECTLY_IGNORED"].includes(v)) return "green";
  if (["MEDIUM", "PENDING", "PENDING_VERIFICATION", "SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS", "SCHEDULED", "UNDER_REVIEW", "PROSPECT", "IGNORED", "SUPERSEDED"].includes(v)) return "amber";
  if (["HIGH", "EXPIRED", "REJECTED", "INCOMPLETE", "OPEN", "OVERDUE", "SUSPENDED", "CRITICAL", "FAIL", "FALSE_NEGATIVE", "CONTROL_WRONGLY_FLAGGED", "UNLABELLED_FINDING"].includes(v)) return "red";
  return "grey";
}

export function Badge({ value }) {
  if (value === null || value === undefined || value === "") return <span className="muted">–</span>;
  return <span className={`badge ${tone(value)}`}>{String(value).replaceAll("_", " ")}</span>;
}

export function Loading() { return <div className="muted pad">Loading…</div>; }

export function ErrorBox({ error }) {
  return <div className="error">Could not load data: {String((error && error.message) || error)}</div>;
}

export function Card({ title, right, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-head"><h2>{title}</h2><div>{right}</div></div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, to, bad }) {
  const body = (
    <div className={`stat ${bad ? "bad" : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
  return to ? <Link to={to} className="stat-link">{body}</Link> : body;
}

/** Horizontal bars from an object like {APPROVED: 120, PROSPECT: 30}. linkFor(key) makes a bar clickable. */
export function BarList({ data, linkFor }) {
  const entries = Object.entries(data || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <div className="muted">No data</div>;
  return (
    <div className="bars">
      {entries.map(([k, v]) => {
        const label = <span className="bar-label">{k.replaceAll("_", " ")}</span>;
        return (
          <div className="bar-row" key={k}>
            {linkFor ? <Link to={linkFor(k)}>{label}</Link> : label}
            <div className="bar-track"><div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></div>
            <span className="bar-value">{fmtNum(v)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function DataTable({ columns, rows, empty = "No rows match these filters." }) {
  if (!rows || rows.length === 0) return <div className="muted pad">{empty}</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.label}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || r.document_id || r.review_id || r.alert_id || r.event_id || r.customer_id || i}>
              {columns.map((c) => <td key={c.label} className={c.className}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pager({ data, onPage }) {
  if (!data || data.pages <= 1) return null;
  return (
    <div className="pager">
      <button disabled={data.page <= 1} onClick={() => onPage(1)}>« First</button>
      <button disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>‹ Prev</button>
      <span>Page {data.page} of {data.pages}</span>
      <button disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>Next ›</button>
      <button disabled={data.page >= data.pages} onClick={() => onPage(data.pages)}>Last »</button>
    </div>
  );
}

const norm = (o) => (typeof o === "string" ? { value: o, label: o.replaceAll("_", " ") } : o);

/** fields: [{name, label, type: "text"|"select"|"date", options}] */
export function FilterBar({ fields, filters, onChange, onReset }) {
  return (
    <div className="filters">
      {fields.map((f) => (
        <label key={f.name}>
          <span>{f.label}</span>
          {f.type === "select" ? (
            <select value={filters[f.name] ?? ""} onChange={(e) => onChange(f.name, e.target.value)}>
              <option value="">All</option>
              {(f.options || []).map(norm).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ) : (
            <input
              type={f.type === "date" ? "date" : "text"}
              value={filters[f.name] ?? ""}
              placeholder={f.placeholder || ""}
              onChange={(e) => onChange(f.name, e.target.value)}
            />
          )}
        </label>
      ))}
      <button className="ghost" onClick={onReset}>Reset</button>
    </div>
  );
}

/** A complete list screen: filters + table + pager, all driven by one real endpoint. */
export function ListPage({ title, subtitle, path, defaults, fields, columns, pageSize = 25 }) {
  const p = usePaged(path, defaults, pageSize);
  return (
    <div>
      <h1>{title}</h1>
      {subtitle && <p className="muted">{subtitle}</p>}
      <FilterBar fields={fields} filters={p.filters} onChange={p.setFilter} onReset={p.reset} />
      {p.error && <ErrorBox error={p.error} />}
      {p.loading && !p.data && <Loading />}
      {p.data && (
        <>
          <div className="muted small">{fmtNum(p.data.total)} results{p.loading ? " (updating…)" : ""}</div>
          <DataTable columns={columns} rows={p.data.items} />
          <Pager data={p.data} onPage={p.setPage} />
        </>
      )}
    </div>
  );
}

export function CompletenessBar({ percent, label }) {
  return (
    <div className="comp">
      <div className="bar-track small-track"><div className={`bar-fill ${tone(label)}`} style={{ width: `${percent}%` }} /></div>
      <span className="small">{fmtPct(percent)}</span>
    </div>
  );
}
