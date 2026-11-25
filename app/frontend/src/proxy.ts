import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextFetchEvent, NextMiddleware, NextRequest, NextResponse } from "next/server";
import { isClerkServerEnabled } from "@/lib/auth-server";
import { signGuestCookieValue, verifyGuestCookieValue } from "@/lib/guest-cookie";

async function applyGuestSession(req: NextRequest): Promise<NextResponse> {
  const verified = await verifyGuestCookieValue(req.cookies.get("medquest_guest_session")?.value);
  let guestId: string;
  let mustSetCookie = false;

  if (!verified) {
    guestId = crypto.randomUUID().toLowerCase();
    mustSetCookie = true;
  } else {
    guestId = verified.guestId;
    mustSetCookie = verified.needsResign || !req.cookies.has("medquest_guest_session");
  }

  // Clone request headers and overwrite the internal identity header.
  // Never trust any identity header sent directly from the browser.
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-internal-guest-id", guestId);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  // Persist signed cookie on the response if newly created or needs rotation
  if (mustSetCookie) {
    const signedValue = await signGuestCookieValue(guestId);
    response.cookies.set("medquest_guest_session", signedValue, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 365, // 1 year
    });
  }

  return response;
}

let cachedClerkHandler: NextMiddleware | null = null;

function getClerkHandler(): NextMiddleware {
  if (!cachedClerkHandler) {
    cachedClerkHandler = clerkMiddleware(async (_auth, req) => applyGuestSession(req));
  }
  return cachedClerkHandler;
}

export default async function proxy(req: NextRequest, event: NextFetchEvent) {
  if (!isClerkServerEnabled()) {
    return applyGuestSession(req);
  }
  return getClerkHandler()(req, event);
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
    // Clerk's Frontend API proxy serves its browser bundle from this path.
    "/__clerk/(.*)",
  ],
};
