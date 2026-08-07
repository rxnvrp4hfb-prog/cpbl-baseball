# CPBL Live Board on Cloudflare Pages

This deploy target serves the app at the root custom domain:

```text
https://baseball.leokuo.com/
```

It also keeps `/baseball/` available for the old path.

The frontend calls the same-origin API:

```text
https://baseball.leokuo.com/api/games
https://baseball.leokuo.com/api/game
```

If direct CPBL requests from Cloudflare are blocked, deploy `../cpbl-proxy` to a non-Cloudflare Node host and set this Cloudflare Pages environment variable:

```text
CPBL_PROXY_BASE_URL=https://your-proxy.example.com
```

## Deploy

Cloudflare Pages GitHub settings:

```text
Root directory: cloudflare-pages
Build command: npm run build
Build output directory: public
```

Do not deploy only the root `index.html`, because Cloudflare will not deploy the `functions/` API routes.

```bash
cd cpbl-live-dashboard/cloudflare-pages
npm install
npm run deploy
```

Then add `baseball.leokuo.com` as the Cloudflare Pages custom domain.

## API Notes

`/api/games` and `/api/game` are Cloudflare Pages Functions. If they return HTML, the project was deployed without the `functions/` directory.

Direct CPBL access from Cloudflare may fail with errors such as `Network connection lost.`. In that case:

1. Deploy `../cpbl-proxy` to Vercel, Render, Railway, Fly.io, or another non-Cloudflare Node host.
2. Set Cloudflare Pages environment variable:

```text
CPBL_PROXY_BASE_URL=https://your-cpbl-proxy.example.com
```

3. Redeploy Cloudflare Pages.
