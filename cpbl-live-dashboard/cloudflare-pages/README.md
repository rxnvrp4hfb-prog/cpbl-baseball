# CPBL Live Board on Cloudflare Pages

This deploy target serves the app at:

```text
https://leokuo.com/baseball/
```

The root page only redirects to `/baseball/`; the CPBL board itself is not served as the root app.

## Deploy

```bash
cd cpbl-live-dashboard/cloudflare-pages
npm install
npm run deploy
```

Then add `leokuo.com` as the Cloudflare Pages custom domain.

