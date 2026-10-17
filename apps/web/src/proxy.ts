import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "paa_session";
const PUBLIC_PATHS = ["/login", "/register"];
// Client-supplied forwarding headers would let anyone pick the IP the API rate-limits on.
const SPOOFABLE_HEADERS = ["x-forwarded-for", "x-real-ip", "forwarded"];

/**
 * 1. API requests: strip forwarding headers before Next.js proxies them to FastAPI.
 * 2. Pages: UX-only redirect to sign-in when there is no session cookie. This is NOT the security
 *    boundary; the API checks the session on every request.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api/")) {
    const headers = new Headers(request.headers);
    for (const name of SPOOFABLE_HEADERS) headers.delete(name);
    return NextResponse.next({ request: { headers } });
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (isPublic || request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Skip Next internals and static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
