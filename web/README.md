# paic-web

Vite + React 18 + TypeScript + Tailwind CSS 3 SPA for the Prisma Access IP Console.

## Development

```bash
# Install dependencies
npm install

# Start dev server (proxies /api/* to localhost:8080)
npm run dev
```

## Build

```bash
npm run build
# Output lands in ../src/paic/static/ — shipped inside the Python package
```

## Lint

```bash
npm run lint
```

## Pages

| Route | Description |
|---|---|
| `/tenants` | Manage Prisma Access tenants, test API credentials |
| `/profiles` | Aggregation profiles (mode, format, filter spec, cron) |
| `/reports` | Export prefix data in various formats |
| `/diffs` | Per-tenant IP prefix change history |

## Stack

- **React 18** + **React Router v6**
- **@tanstack/react-query v5** for data fetching
- **Tailwind CSS 3** with `dark:` class variant
- **DM Sans** / **DM Mono** fonts (Google Fonts)
