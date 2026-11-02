# Vodacom INTEL Operations — Frontend

Enterprise-grade internal operations platform for the Vodacom INTSS team.

Built with **Next.js 15 · React 19 · Tailwind CSS v4 · Framer Motion · TanStack Query · Recharts**.

---

## Quick Start

### 1. Prerequisites
- Node.js 22+
- The ITIL Group Reports API running at `http://127.0.0.1:8000`

### 2. Install

```bash
cd vodacom-itil-reports-fe
npm install
```

### 3. Configure environment

```bash
cp .env.local.example .env.local
# Local default proxies /api to http://127.0.0.1:8000
```

### 4. Run development server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 5. Production build

```bash
npm run build
npm start
```

For QA and production release packaging, Podman deployment, rollback, and
health-check procedures, see [docs/frontend-deployment-mop.md](docs/frontend-deployment-mop.md).

---

## Application Structure

```
src/
├── app/
│   ├── login/                  ← Login page (JWT auth)
│   ├── workspace/
│   │   ├── page.tsx            ← Dashboard — KPIs, division tables, charts
│   │   ├── records/page.tsx    ← Records grid — filters, SLA countdown, pagination
│   │   └── sla/page.tsx        ← SLA Monitor — live division breakdown
│   ├── daily-report/
│   │   └── page.tsx            ← INTSS Daily Report — locked matrix
│   ├── divisions/
│   │   └── page.tsx            ← Division admin — group management
│   └── admin/
│       ├── pipeline/page.tsx   ← Pipeline status + run log
│       ├── audit/page.tsx      ← Audit log (Super Admin)
│       ├── users/page.tsx      ← User management (Super Admin)
│       └── change-password/    ← Forced password change on first login
├── components/
│   ├── layout/AppShell.tsx     ← Topbar + sidebar shell
│   └── ui/index.tsx            ← Design system components
├── lib/
│   ├── api.ts                  ← API client (all endpoints)
│   ├── auth-context.tsx        ← Auth state + JWT management
│   ├── query-provider.tsx      ← TanStack Query setup
│   └── utils.ts                ← Formatters, helpers, style maps
└── types/index.ts              ← All TypeScript types (API-aligned)
```

---

## Environment Variables

| Variable              | Default                   | Description |
|-----------------------|---------------------------|-------------|
| `NEXT_PUBLIC_API_URL` | empty                     | Browser-facing backend API base URL. Leave empty to call same-origin `/api`. |
| `API_PROXY_URL`       | `http://127.0.0.1:8000`   | Server-side target for Next.js `/api/*` rewrites. |

For deployment, either keep `NEXT_PUBLIC_API_URL` empty and set `API_PROXY_URL` to the backend origin, or set `NEXT_PUBLIC_API_URL` to the public backend origin if the backend handles CORS directly.

---

## QA Docker Deployment

Recommended QA deployment is Docker Compose on the Linux server. The frontend runs as a standalone Next.js container and proxies browser `/api/*` requests to the backend through `API_PROXY_URL`.

### Server prerequisites

- Docker Engine
- Docker Compose v2
- Backend API reachable from the frontend container

### Deploy

```bash
cp .env.qa.example .env.qa
# Edit API_PROXY_URL in .env.qa
chmod +x deploy-qa.sh
./deploy-qa.sh
```

The app will be available on host port `3001` by default:

```bash
curl http://localhost:3001/healthz
docker compose -f docker-compose.qa.yml logs -f
```

If the backend runs directly on the same Linux host, use:

```bash
API_PROXY_URL=http://host.docker.internal:8000
```

If the backend is another Compose service, use the backend service name, for example:

```bash
API_PROXY_URL=http://api:8000
```

For HTTPS and a QA hostname, put Nginx or your company reverse proxy in front of this container and forward traffic to `127.0.0.1:3001`.

---

## Features

### Operations Workspace
- **Dashboard** — KPI cards, breach trend chart, category donut, division summary tables
- **Records** — Full filter bar (SLA chips, division, category, search), live SLA countdown ticker, paginated grid
- **SLA Monitor** — Per-division status panels with category breakdown

### INTSS Daily Report
- Locked to TSS Operational Support · IN TELECOMS · IN PPS
- Exact Excel pivot matrix: groups × SLA bands × categories
- KPI cards, category split bar, print-friendly

### Division Admin
- Create divisions, add/remove assignee groups
- Activity log with expandable JSON details

### Admin
- Pipeline status with run log
- User management (Super Admin only)
- Audit log (Super Admin only)
- Forced password change on first login

---

## Design System

**Palette** — Vodacom red `#E60000` as primary brand, light grey `#F5F5F5` as base background, white `#FFFFFF` for cards and panels, `#E5E5E5` borders.

**Typography** — Inter variable for UI, JetBrains Mono for IDs, timestamps, and numeric data.

**Motion** — Page transitions via Framer Motion `AnimatePresence`, staggered list reveals, smooth bar charts, live breach countdown ticking every second.

**SLA colours** — Red for breached, amber for nearing, blue for no-schedule, green for within SLA. Applied consistently across badges, row highlights, and KPI cards.
