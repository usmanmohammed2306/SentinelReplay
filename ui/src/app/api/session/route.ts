import { cookies } from "next/headers";
import { apiBase, SESSION, sameOrigin, boundedBody } from "@/lib/server";

export async function POST(request: Request) {
  if (!sameOrigin(request))
    return Response.json({ detail: "Origin rejected" }, { status: 403 });
  let token: unknown;
  try {
    token = JSON.parse(
      new TextDecoder().decode(await boundedBody(request, 8192)),
    ).token;
  } catch (error) {
    return new Response(null, {
      status: error instanceof RangeError ? 413 : 400,
    });
  }
  if (typeof token !== "string" || token.length < 32 || token.length > 4096)
    return Response.json({ detail: "Invalid access token" }, { status: 401 });
  try {
    const result = await fetch(apiBase() + "/v1/runs?limit=1", {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    if (!result.ok)
      return Response.json(
        { detail: "Access denied" },
        { status: result.status === 503 ? 503 : 401 },
      );
  } catch {
    return Response.json(
      { detail: "Evidence API is unavailable" },
      { status: 503 },
    );
  }
  (await cookies()).set(SESSION, token, {
    httpOnly: true,
    sameSite: "strict",
    secure:
      new URL(process.env.SENTINEL_UI_ORIGIN ?? request.url).protocol ===
      "https:",
    path: "/",
    maxAge: 28800,
  });
  return Response.json(
    { authenticated: true },
    { headers: { "Cache-Control": "no-store" } },
  );
}
export async function DELETE(request: Request) {
  if (!sameOrigin(request)) return new Response(null, { status: 403 });
  (await cookies()).delete(SESSION);
  return Response.json({ authenticated: false });
}
