# Liquid+ frontend

React 18 + Vite + Recharts. Plain JavaScript and one hand-written stylesheet.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on 127.0.0.1:8000
npm test         # 15 tests (Vitest + Testing Library); on low-memory machines add --no-file-parallelism
npm run build    # production build in dist/
```

Change the backend address with `VITE_PROXY_TARGET` in `.env` (copy `.env.example`).

```
src/
  api.js           fetch wrapper, token handling, useFetch hook
  auth.jsx         login state
  filters.jsx      run date, location and currency shared by all pages
  format.js        number formatting, colours, constants
  components/      layout, ladder chart, tables, drill-down, rationale panel
  pages/           one file per screen (Data = uploads + models, support users only)
  test/            unit and page tests; fixtures.json holds real API responses
```
