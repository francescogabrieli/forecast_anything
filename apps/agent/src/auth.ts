import { createHash, timingSafeEqual } from "node:crypto";

export function bridgeAuthorized(request: Request, token?: string): boolean {
  if (!token) return false;
  const header = request.headers.get("authorization") ?? "";
  const match = /^Bearer ([^\s]+)$/.exec(header);
  if (!match) return false;
  const expected = createHash("sha256").update(token).digest();
  const supplied = createHash("sha256").update(match[1]).digest();
  return timingSafeEqual(expected, supplied);
}
