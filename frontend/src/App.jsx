import React from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import Customers from "./pages/Customers.jsx";
import CustomerDetail from "./pages/CustomerDetail.jsx";
import Documents from "./pages/Documents.jsx";
import Businesses from "./pages/Businesses.jsx";
import Reviews from "./pages/Reviews.jsx";
import Alerts from "./pages/Alerts.jsx";
import Exceptions from "./pages/Exceptions.jsx";
import Audit from "./pages/Audit.jsx";
import DataQuality from "./pages/DataQuality.jsx";

const NAV = [
  ["/", "Dashboard"], ["/customers", "Customers"], ["/documents", "Documents"], ["/businesses", "Businesses & ownership"],
  ["/reviews", "Reviews"], ["/alerts", "Alerts"], ["/exceptions", "Exceptions"], ["/audit", "Audit trail"],
  ["/quality", "Data quality"],
];

export default function App() {
  const { search } = useLocation();   // used as a key so links like /documents?state=EXPIRED reload the filters
  return (
    <div className="shell">
      <nav>
        <div className="brand">KYC Evidence System<small>YottaFlex AI challenge</small></div>
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
        ))}
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/customers" element={<Customers key={search} />} />
          <Route path="/customers/:id" element={<CustomerDetail />} />
          <Route path="/documents" element={<Documents key={search} />} />
          <Route path="/businesses" element={<Businesses key={search} />} />
          <Route path="/reviews" element={<Reviews key={search} />} />
          <Route path="/alerts" element={<Alerts key={search} />} />
          <Route path="/exceptions" element={<Exceptions key={search} />} />
          <Route path="/audit" element={<Audit key={search} />} />
          <Route path="/quality" element={<DataQuality />} />
          <Route path="*" element={<div><h1>Page not found</h1></div>} />
        </Routes>
      </main>
    </div>
  );
}
