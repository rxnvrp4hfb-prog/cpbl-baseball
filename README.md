# CPBL Cloudflare Pages Deploy

Upload these files to the root of the GitHub repository connected to Cloudflare Pages.

Cloudflare Pages settings:

- Root directory: blank
- Build command: `npm run build`
- Build output directory: `public`

After deployment, test:

`https://baseball.leokuo.com/api/games?ping=1`

Expected response:

`{"ok":true,"status":"api alive",...}`
