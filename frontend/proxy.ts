import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// must match backend/app/cookies.py SESSION_COOKIE_NAME.
const SESSION_COOKIE = "kairo_session";

// fast logged-out pre-check only: no session cookie -> definitely logged out,
// so redirect server-side with zero flash and zero backend round-trip.
// cookie presence proves nothing (it may be expired/revoked), and the edge
// runtime cannot validate the backend's httponly session without calling the
// backend anyway, so validation stays in the pages: they own the 401 (/login)
// vs backend-down (error UI) split via /auth/me. see app/chat/page.tsx.
export default function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/chat/:path*"],
};
