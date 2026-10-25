// Public availability flags only; authentication remains in each application.
const availability = new Map();
const BRIDGE_PATHS = new Set(['/qlab/bridge-playback','/qlab/bridge-catalog','/qlab/bridge-diagnostics','/qlab/bridge-events','/qlab/bridge-control']);
export function pausePage(unavailable = false) {
  const title = unavailable ? 'Service Unavailable' : '404 Not Found';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>${title}</title></head><body><h1>${title}</h1></body></html>`;
}
export async function websiteGate(request, siteId, options = {}) {
  const path = new URL(request.url).pathname;
  if (path === '/site-availability.js' || (options.keepBridge && BRIDGE_PATHS.has(path))) return null;
  const cached = availability.get(siteId);
  let enabled = cached?.enabled;
  let unavailable = false;
  if (!cached || cached.until <= Date.now()) {
    try {
      const response = await fetch(`https://api.leokuo.com/sites/${siteId}/status`, { signal: AbortSignal.timeout(5000) });
      const data = await response.json();
      if (!response.ok || !data.ok || typeof data.enabled !== 'boolean') throw Error('status unavailable');
      enabled = data.enabled;
      availability.set(siteId, { enabled, until: Date.now() + 60_000 });
    } catch {
      // Keep the last known state during a temporary control-service outage.
      if (enabled === undefined) unavailable = true;
    }
  }
  if (enabled === true) return null;
  const headers = { 'cache-control':'no-store','retry-after':'60','x-site-state':unavailable?'unavailable':'closed','x-content-type-options':'nosniff' };
  if (request.method !== 'GET' && request.method !== 'HEAD' || request.headers.get('accept')?.includes('application/json')) return Response.json({ok:false,siteClosed:!unavailable,error:unavailable?'service unavailable':'not found'},{status:unavailable?503:404,headers});
  return new Response(request.method==='HEAD'?null:pausePage(unavailable),{status:unavailable?503:404,headers:{...headers,'content-type':'text/html; charset=utf-8','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}});
}
