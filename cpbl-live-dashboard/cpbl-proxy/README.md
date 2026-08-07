# CPBL Proxy

Small Node 20 proxy for Cloudflare Pages Functions.

It exposes:

```text
GET  /health
POST /cpbl
```

Optional protection:

```bash
export CPBL_PROXY_TOKEN="change-me"
```

Then set the same token on Cloudflare Pages as `CPBL_PROXY_TOKEN`, and set `CPBL_PROXY_BASE_URL` to the deployed proxy URL.
