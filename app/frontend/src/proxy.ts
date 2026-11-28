import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextFetchEvent, NextMiddleware, NextRequest, NextResponse } from "next/server";
import { isClerkServerEnabled } from "@/lib/auth-server";
import { isE2EAuthBypassEnabled } from "@/lib/e2e-auth";

const isPublicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/__clerk(.*)",
  "/api/images(.*)",
  "/api/v1/images(.*)",
  "/api/notifications/cron/dispatch",
  "/api/v1/notifications/cron/dispatch",
  "/api/lessons/(.*)/stream",
  "/api/v1/lessons/(.*)/stream",
]);

let cachedClerkHandler: NextMiddleware | null = null;

function getClerkHandler(): NextMiddleware {
  if (!cachedClerkHandler) {
    cachedClerkHandler = clerkMiddleware(async (auth, req) => {
      if (isPublicRoute(req)) {
        return NextResponse.next();
      }
      const { userId } = await auth();
      if (!userId) {
        if (req.nextUrl.pathname.startsWith("/api/")) {
          return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
        }
        const signInUrl = new URL("/sign-in", req.url);
        const target = `${req.nextUrl.pathname}${req.nextUrl.search}`;
        if (target && target !== "/" && !target.startsWith("/sign-in")) {
          signInUrl.searchParams.set("redirect_url", target);
        }
        return NextResponse.redirect(signInUrl);
      }
      return NextResponse.next();
    });
  }
  return cachedClerkHandler;
}

export default async function proxy(req: NextRequest, event: NextFetchEvent) {
  if (isE2EAuthBypassEnabled()) {
    return NextResponse.next();
  }
  if (!isClerkServerEnabled()) {
    if (isPublicRoute(req)) {
      return NextResponse.next();
    }
    return NextResponse.json({ error: "Clerk desabilitado neste ambiente." }, { status: 503 });
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
