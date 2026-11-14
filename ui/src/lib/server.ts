import "server-only";
import { cookies } from "next/headers";

export const SESSION = "sentinel_session";
export function apiBase(): string {
  const url = new URL(process.env.SENTINEL_API_URL ?? "http://127.0.0.1:8000");
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error("Invalid configured API base URL");
  }
  return url.origin;
}
export async function sessionToken() {
  return (await cookies()).get(SESSION)?.value;
}
export async function boundedBody(
  request: Request,
  limit: number,
): Promise<Uint8Array> {
  if (!request.body) return new Uint8Array();
  const declared = request.headers.get("content-length");
  if (
    declared !== null &&
    (!/^\d+$/.test(declared) || Number(declared) > limit)
  )
    throw new RangeError("Request exceeds byte budget");
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > limit) {
      await reader.cancel();
      throw new RangeError("Request exceeds byte budget");
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.length;
  }
  return body;
}
export function sameOrigin(request: Request): boolean {
  const host = request.headers.get("host");
  if (!host) return false;
  const origin = request.headers.get("origin");
  const configured = process.env.SENTINEL_UI_ORIGIN;
  if (configured)
    return origin === configured && host === new URL(configured).host;
  const expected = new URL(new URL(request.url).protocol + "//" + host);
  return (
    ["127.0.0.1", "localhost", "[::1]"].includes(expected.hostname) &&
    origin === expected.origin
  );
}
