export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/tts") {
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(request) });
      if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, request);
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
  return { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, OPTIONS", Vary: "Origin" };
}

function json(value, status, request) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors(request) } });
}
