# PharmacoAI Landing

Standalone marketing landing page extracted from the main PharmacoAI frontend. Vite + React, no backend dependencies — designed to deploy to Vercel as a static site.

## Local dev

```bash
npm install
npm run dev      # http://127.0.0.1:5174
npm run build    # outputs to dist/
npm run preview  # serves the production build locally
```

## Deploy to Vercel

This is a stock Vite project — Vercel auto-detects it.

1. Push this folder to a Git repo (or use the Vercel CLI: `npx vercel`).
2. In Vercel, "New Project" → import the repo → set **Root Directory** to `landing` if you're deploying the whole monorepo.
3. Framework preset: **Vite**. Build command: `npm run build`. Output directory: `dist`.
4. Deploy.

## Hooking up the CTAs

`#` placeholders are used for "Pharmacist Login", "Manage Users", "Admin", "Pharmacist", and "Learn more" links. Point them at your main app URL when you're ready.

## Styling

Tailwind is loaded via the CDN (`<script src="https://cdn.tailwindcss.com...">`) with a custom theme defined inline in `index.html`. This matches the parent frontend's setup so the design tokens (`primary`, `secondary`, `surface-container-*`, etc.) resolve identically.

For production you may want to migrate to a real Tailwind build (PostCSS or `@tailwindcss/vite`) to drop the CDN runtime — but the CDN works fine for a marketing page.
