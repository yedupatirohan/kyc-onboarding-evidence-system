import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api.js";

/** Fetch one endpoint; refetches when path or params change. */
export function useApi(path, params = {}) {
  const key = path + JSON.stringify(params);
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path, params)
      .then((data) => { if (!cancelled) setState({ data, error: null, loading: false }); })
      .catch((error) => { if (!cancelled) setState({ data: null, error, loading: false }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

/** A paginated, filterable list. Initial filter values can come from the URL (?status=APPROVED). */
export function usePaged(path, defaults = {}, pageSize = 25) {
  const [search] = useSearchParams();
  const initial = useMemo(() => {
    const f = { ...defaults };
    Object.keys(defaults).forEach((k) => {
      const v = search.get(k);
      if (v !== null) f[k] = v;
    });
    return f;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [filters, setFilters] = useState(initial);
  const [page, setPage] = useState(1);
  const state = useApi(path, { ...filters, page, page_size: pageSize });
  const setFilter = (name, value) => { setFilters((f) => ({ ...f, [name]: value })); setPage(1); };
  const reset = () => { setFilters(defaults); setPage(1); };
  return { ...state, filters, setFilter, reset, page, setPage };
}
