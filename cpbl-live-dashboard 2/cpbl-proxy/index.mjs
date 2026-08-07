import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

const CPBL_PUBLIC = "https://www.cpbl.com.tw";
const CPBL_ORIGIN = process.env.CPBL_ORIGIN || CPBL_PUBLIC;
const CPBL_HOST = "www.cpbl.com.tw";
const UA = "Mozilla/5.0";
const CPBL_HEADERS = {
  "User-Agent": UA,
  "Accept-Encoding": "identity",
  Accept: "*/*",
  Connection: "keep-alive",
  "Accept-Language": "zh-TW,zh;q=0.9",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function headerGetter(headers) {
  return {
    get(name) {
      const value = headers[String(name).toLowerCase()];
      return Array.isArray(value) ? value.join(", ") : value || "";
    },
  };
}

function cpblRequest(path, init = {}, redirectCount = 0) {
  return new Promise((resolve, reject) => {
    const body = init.body == null ? null : String(init.body);
    const headers = {
      ...(init.headers || {}),
      ...(body ? { "Content-Length": Buffer.byteLength(body) } : {}),
    };
    const target = new URL(`${CPBL_ORIGIN}${path}`);
    const requestImpl = target.protocol === "https:" ? httpsRequest : httpRequest;
    const req = requestImpl(
      target,
      {
        method: init.method || "GET",
        headers,
        servername: CPBL_HOST,
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && redirectCount < 5) {
            const nextUrl = new URL(res.headers.location, `${CPBL_ORIGIN}${path}`);
            const nextPath = `${nextUrl.pathname}${nextUrl.search}`;
            const redirectCookie = cookiesFrom({ headers: headerGetter(res.headers) });
            const nextInit = {
              ...init,
              headers: {
                ...(init.headers || {}),
                ...(redirectCookie
                  ? { Cookie: mergeCookies(init.headers?.Cookie || init.headers?.cookie || "", redirectCookie) }
                  : {}),
              },
            };
            cpblRequest(nextPath, nextInit, redirectCount + 1).then(resolve, reject);
            return;
          }
          resolve({
            ok: res.statusCode >= 200 && res.statusCode < 300,
            status: res.statusCode,
            headers: headerGetter(res.headers),
            text: async () => text,
            json: async () => JSON.parse(text),
          });
        });
      },
    );
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function inputValue(html, name) {
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(
    `name=["']${esc}["'][^>]*value=["']([^"']*)["']|value=["']([^"']*)["'][^>]*name=["']${esc}["']`,
    "i",
  );
  const m = String(html || "").match(re);
  return m ? (m[1] ?? m[2] ?? "") : "";
}

function cookiesFrom(response) {
  const raw = response.headers.get("set-cookie") || "";
  return raw
    .split(/,(?=[^;,]+=)/)
    .map((x) => x.split(";")[0].trim())
    .filter(Boolean)
    .join("; ");
}

function mergeCookies(...cookieStrings) {
  const jar = new Map();
  for (const cookieString of cookieStrings) {
    for (const item of String(cookieString || "").split(";")) {
      const cookie = item.trim();
      const eq = cookie.indexOf("=");
      if (eq > 0) jar.set(cookie.slice(0, eq), cookie);
    }
  }
  return [...jar.values()].join("; ");
}

async function cpblSession() {
  const response = await cpblRequest("/", {
    headers: CPBL_HEADERS,
  });
  const html = await response.text();
  const token = inputValue(html, "__RequestVerificationToken");
  if (!response.ok) throw new Error(`CPBL 首頁回應 ${response.status}`);
  if (!token) throw new Error("找不到 CPBL 驗證 token");
  return { token, cookie: cookiesFrom(response) };
}

async function postCpbl(path, payload) {
  const session = await cpblSession();
  const body = new URLSearchParams({ __RequestVerificationToken: session.token, ...payload });
  const response = await cpblRequest(path, {
    method: "POST",
    body,
    headers: {
      ...CPBL_HEADERS,
      "Content-Type": "application/x-www-form-urlencoded",
      "X-Requested-With": "XMLHttpRequest",
      Referer: `${CPBL_PUBLIC}/`,
      ...(session.cookie ? { Cookie: session.cookie } : {}),
    },
  });
  if (!response.ok) throw new Error(`CPBL API 回應 ${response.status}`);
  return response.json();
}

async function postCpblLive(payload) {
  const year = String(payload.Year || payload.year || "");
  const kindCode = String(payload.KindCode || payload.kindCode || "");
  const gameSno = String(payload.GameSno || payload.gameSno || "");
  const referer = `${CPBL_PUBLIC}/box/live?year=${year}&kindCode=${kindCode}&gameSno=${gameSno}`;
  const pagePath = `/box/live?year=${year}&kindCode=${kindCode}&gameSno=${gameSno}`;
  const page = await cpblRequest(pagePath, {
    headers: CPBL_HEADERS,
  });
  const html = await page.text();
  const body = new URLSearchParams({
    __RequestVerificationToken: inputValue(html, "__RequestVerificationToken"),
    GameSno: gameSno,
    KindCode: kindCode,
    Year: year,
    PrevOrNext: inputValue(html, "PrevOrNext") || "0",
  });
  let cookie = cookiesFrom(page);
  const response = await cpblRequest("/box/getlive", {
    method: "POST",
    body,
    headers: {
      ...CPBL_HEADERS,
      "Content-Type": "application/x-www-form-urlencoded",
      "X-Requested-With": "XMLHttpRequest",
      Referer: referer,
      ...(cookie ? { Cookie: cookie } : {}),
    },
  });
  cookie = mergeCookies(cookie, cookiesFrom(response));
  if (!response.ok) throw new Error(`CPBL live API 回應 ${response.status}`);
  return response.json();
}

function authorized(request) {
  const token = process.env.CPBL_PROXY_TOKEN || "";
  if (!token) return true;
  return request.headers.get("authorization") === `Bearer ${token}`;
}

export async function handleRequest(request) {
  const url = new URL(request.url);
  if (request.method === "GET" && url.pathname === "/health") return json({ ok: true });
  if (request.method !== "POST" || url.pathname !== "/cpbl") return json({ ok: false, error: "not found" }, 404);
  if (!authorized(request)) return json({ ok: false, error: "unauthorized" }, 401);

  try {
    const body = await request.json();
    const path = String(body.path || "");
    if (!["/home/getdetaillist", "/home/gamedetail", "/box/getlive"].includes(path)) {
      return json({ ok: false, error: "path not allowed" }, 400);
    }
    const data = path === "/box/getlive" ? await postCpblLive(body.payload || {}) : await postCpbl(path, body.payload || {});
    return json({ ok: true, data });
  } catch (error) {
    return json({ ok: false, error: error?.message || String(error) }, 502);
  }
}

export default async function vercelHandler(req, res) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const request = new Request(`https://${req.headers.host}${req.url}`, {
    method: req.method,
    headers: req.headers,
    body: chunks.length ? Buffer.concat(chunks) : undefined,
  });
  const response = await handleRequest(request);
  res.writeHead(response.status, Object.fromEntries(response.headers));
  res.end(Buffer.from(await response.arrayBuffer()));
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const port = Number(process.env.PORT || 8788);
  createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const request = new Request(`http://127.0.0.1:${port}${req.url}`, {
      method: req.method,
      headers: req.headers,
      body: chunks.length ? Buffer.concat(chunks) : undefined,
    });
    const response = await handleRequest(request);
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  }).listen(port, "127.0.0.1", () => {
    console.log(`CPBL proxy listening on http://127.0.0.1:${port}`);
  });
}
