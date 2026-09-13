export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Same-origin SSE proxy.
 *
 * Next.js rewrites buffer the upstream stream, so the live answer path
 * used to point the browser at NEXT_PUBLIC_STREAM_BASE (a different
 * origin). That drop the HttpOnly session cookie. This route pipes the
 * backend stream through so cookies stay same-origin and the rewrite
 * never sees the body.
 */
function backendOrigin(): string {
  const proxy = process.env.API_PROXY_URL;
  if (proxy) {
    return proxy.replace(/\/api\/:path\*$/, "").replace(/\/$/, "");
  }
  return (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  const cookie = request.headers.get("cookie") ?? "";
  const apiKey = request.headers.get("x-atlas-api-key") ?? "";
  const upstream = await fetch(
    `${backendOrigin()}/api/sessions/${sessionId}/messages/stream`,
    {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        Cookie: cookie,
        "X-Atlas-API-Key": apiKey,
      },
      body: await request.text(),
      signal: request.signal,
    },
  );

  const headers = new Headers();
  headers.set(
    "Content-Type",
    upstream.headers.get("content-type") ?? "text/event-stream; charset=utf-8",
  );
  headers.set("Cache-Control", "no-cache, no-transform");
  headers.set("Connection", "keep-alive");
  headers.set("X-Accel-Buffering", "no");

  return new Response(upstream.body, {
    status: upstream.status,
    headers,
  });
}
