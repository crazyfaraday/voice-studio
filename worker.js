export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/session") {
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(request) });
      if (request.method !== "GET") return json({ error: "Method not allowed" }, 405, request);
      const auth = authenticate(request, env);
      return auth.ok ? json({ ok: true, username: auth.username }, 200, request) : json({ error: auth.error }, auth.status, request);
    }
    if (url.pathname === "/api/tts") {
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(request) });
      if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, request);
      const auth = authenticate(request, env);
      if (!auth.ok) return json({ error: auth.error }, auth.status, request);
      if (!env.MINIMAX_API_KEY) return json({ error: "MINIMAX_API_KEY is not configured" }, 503, request);
      try {
        const payload = await request.json();
        if (!String(payload?.text || "").trim()) return json({ error: "text is required" }, 400, request);
        const response = await fetch("https://api.minimaxi.com/v1/t2a_v2", {
          method: "POST",
          headers: { Authorization: `Bearer ${env.MINIMAX_API_KEY}`, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        return new Response(response.body, { status: response.status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors(request) } });
      } catch (error) {
        return json({ error: error.message || "Invalid request" }, 400, request);
      }
    }
    return env.ASSETS.fetch(request);
  },
};

function cors(request) {
  const origin = request.headers.get("Origin") || "https://crazyfaraday.github.io";
  return { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Headers": "Content-Type, X-Voice-Studio-Auth", "Access-Control-Allow-Methods": "GET, POST, OPTIONS", Vary: "Origin" };
}

function json(value, status, request) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors(request) } });
}

function authenticate(request, env) {
  if (!env.VOICE_STUDIO_USERNAME || !env.VOICE_STUDIO_PASSWORD) return { ok: false, status: 503, error: "登录保护尚未完成配置" };
  const value = request.headers.get("X-Voice-Studio-Auth") || "";
  const encoded = value.startsWith("Basic ") ? value.slice(6) : "";
  let decoded = "";
  try { decoded = atob(encoded); } catch {}
  const divider = decoded.indexOf(":");
  const username = divider >= 0 ? decoded.slice(0, divider) : "";
  const password = divider >= 0 ? decoded.slice(divider + 1) : "";
  if (!sameValue(username, env.VOICE_STUDIO_USERNAME) || !sameValue(password, env.VOICE_STUDIO_PASSWORD)) return { ok: false, status: 401, error: "用户名或密码不正确" };
  return { ok: true, username };
}

function sameValue(left, right) {
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index += 1) difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  return difference === 0;
}
