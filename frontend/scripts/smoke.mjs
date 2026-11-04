// Calls every endpoint the 10 screens use, against the REAL running backend, and checks the response shape.
//   1) in backend\:   uvicorn app.main:app          2) in frontend\:   npm run smoke
const BASE = process.env.API_BASE || "http://127.0.0.1:8000/api";

const isList = (d) => Array.isArray(d.items) && typeof d.total === "number" && d.page >= 1 && d.pages >= 0;
const has = (d, keys) => keys.every((k) => k in d);

const CHECKS = [
  ["Dashboard", "/dashboard/summary", (d) => has(d, ["customers", "completeness", "documents", "alerts", "reviews", "exceptions", "evaluation", "reproducibility"])],
  ["Customers list", "/customers?page_size=5", (d) => isList(d) && d.items.length > 0 && has(d.items[0], ["completeness_percent", "risk_level"])],
  ["Customers filter", "/customers?status=APPROVED&risk_level=HIGH&page_size=5", isList],
  ["Customers completeness", "/customers?completeness=COMPLETE&page_size=5", isList],
  ["Customer detail", "/customers/CUS-000001", (d) => has(d, ["completeness", "documents", "reviews", "alerts", "risk_history", "ownership"])],
  ["Documents list", "/documents?page_size=5", (d) => isList(d) && has(d.items[0], ["effective_state", "customer_name"])],
  ["Documents expiring", "/documents?expiring_within_days=30&page_size=5", isList],
  ["Businesses", "/businesses?page_size=5", (d) => isList(d) && has(d.items[0], ["active_ownership_pct", "ownership_exceeds_100"])],
  ["Businesses over 100%", "/businesses?ownership_over_100=true&page_size=5", isList],
  ["Reviews", "/reviews?page_size=5", (d) => isList(d) && has(d.items[0], ["days_overdue", "customer_name"])],
  ["Reviews overdue", "/reviews?overdue=true&page_size=5", isList],
  ["Alerts", "/alerts?page_size=5", (d) => isList(d) && has(d.items[0], ["severity", "customer_name"])],
  ["Exceptions", "/exceptions?page_size=5", (d) => isList(d) && has(d.items[0], ["rule", "expected_decision"])],
  ["Exceptions summary", "/exceptions/summary", (d) => Array.isArray(d) && d.length === 5],
  ["Anomalies vs ground truth", "/anomalies?page_size=5", (d) => isList(d) && has(d.items[0], ["detected", "outcome"])],
  ["Evaluation", "/evaluation", (d) => has(d, ["overall", "per_issue_type", "source"])],
  ["Audit trail", "/audit-events?page_size=5", (d) => isList(d) && has(d.items[0], ["old_value", "new_value"])],
  ["Audit facets", "/audit-events/facets", (d) => has(d, ["entity_types", "actions", "actors"])],
  ["Validation checks", "/validation", (d) => d.total === 12 && Array.isArray(d.checks)],
  ["Validation report", "/validation/report", (d) => d.baseline && d.baseline.clean === true],
  ["Row counts", "/validation/row-counts", (d) => d.tables === 14],
  ["Enums", "/meta/enums", (d) => has(d, ["customer_status", "risk_level", "document_state"])],
  ["Customer types", "/meta/customer-types", (d) => Array.isArray(d) && d.length > 0],
  ["Requirements", "/meta/requirements", (d) => Array.isArray(d) && d.length > 0],
];

let failed = 0;
for (const [name, path, ok] of CHECKS) {
  try {
    const res = await fetch(BASE + path);
    const body = await res.json();
    const pass = res.ok && ok(body);
    if (!pass) failed++;
    console.log(`${pass ? "PASS" : "FAIL"}  ${name.padEnd(26)} ${res.status}  ${path}`);
  } catch (err) {
    failed++;
    console.log(`FAIL  ${name.padEnd(26)} ${err.message}  (is the backend running at ${BASE}?)`);
  }
}
console.log(failed === 0 ? `\nAll ${CHECKS.length} screen endpoints OK` : `\n${failed} of ${CHECKS.length} FAILED`);
process.exit(failed === 0 ? 0 : 1);
