import { apiBase, sameOrigin, sessionToken, boundedBody } from "@/lib/server";

let inflightMutations = 0;

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const token = await sessionToken();
  if (!token || token.length < 32 || token.length > 4096)
    return Response.json(
      { detail: "Sign in to inspect evidence" },
      { status: 401 },
    );
  if (request.method !== "GET" && !sameOrigin(request))
    return new Response(null, { status: 403 });
  const { path } = await context.params;
  if (
    path[0] !== "v1" ||
    path[1] !== "runs" ||
    path.some((part) => !/^[a-zA-Z0-9_.:-]+$/.test(part) || part === "..")
  )
    return new Response(null, { status: 404 });
  let body: Uint8Array | undefined;
  if (request.method === "POST" && request.body) {
    try {
      const authenticated = await fetch(apiBase() + "/v1/runs?limit=1", {
        headers: { Authorization: "Bearer " + token },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      });
      if (!authenticated.ok)
        return new Response(null, { status: authenticated.status });
      await authenticated.body?.cancel();
    } catch {
      return new Response(null, { status: 503 });
    }
    try {
      body = await boundedBody(request, 65 * 1024 * 1024);
    } catch (error) {
      return new Response(null, {
        status: error instanceof RangeError ? 413 : 400,
      });
    }
  }
  const headers: Record<string, string> = { Authorization: "Bearer " + token };
  for (const name of [
    "content-type",
    "x-sentinel-attestation",
    "last-event-id",
  ]) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  try {
    const upstream = await fetch(
      apiBase() +
        "/" +
        path.map(encodeURIComponent).join("/") +
        new URL(request.url).search,
      {
        method: request.method,
        headers,
        body: body as BodyInit | undefined,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(180000),
      },
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json(
      { detail: "Evidence API is unavailable" },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export async function POST(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  if (inflightMutations >= 2)
    return Response.json(
      { detail: "Mutation budget exhausted" },
      { status: 429, headers: { "Retry-After": "1" } },
    );
  inflightMutations++;
  try {
    return await proxy(request, context);
  } finally {
    inflightMutations--;
  }
}
