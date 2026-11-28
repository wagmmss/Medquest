"use client";

import React, { createContext, useCallback, useContext, useEffect } from "react";
import { useAuth, useClerk, useUser } from "@clerk/nextjs";
import { clearClientSessionCaches, syncActiveAuthOwner } from "@/lib/db";

type UserResult = ReturnType<typeof useUser>;
type AuthResult = ReturnType<typeof useAuth>;
type ClerkResult = ReturnType<typeof useClerk>;

interface AppAuthContextValue {
  clerkEnabled: boolean;
  userState: UserResult;
  authState: AuthResult;
  signOut: ClerkResult["signOut"];
}

const FALLBACK_USER_STATE = {
  isLoaded: true,
  isSignedIn: false,
  user: null,
} as unknown as UserResult;

const FALLBACK_AUTH_STATE = {
  isLoaded: true,
  isSignedIn: false,
  userId: null,
  sessionId: null,
  sessionClaims: null,
  actor: null,
  orgId: null,
  orgRole: null,
  orgSlug: null,
  has: () => false,
  signOut: async () => {},
  getToken: async () => null,
} as unknown as AuthResult;

const FALLBACK_CONTEXT_VALUE: AppAuthContextValue = {
  clerkEnabled: false,
  userState: FALLBACK_USER_STATE,
  authState: FALLBACK_AUTH_STATE,
  signOut: (async () => {}) as unknown as ClerkResult["signOut"],
};

const AppAuthContext = createContext<AppAuthContextValue>(FALLBACK_CONTEXT_VALUE);

function ClerkAuthBridge({ children }: { children: React.ReactNode }) {
  const userState = useUser();
  const authState = useAuth();
  const { signOut: clerkSignOut } = useClerk();

  useEffect(() => {
    const resolvedUserId = userState.user?.id ?? authState.userId ?? null;
    syncActiveAuthOwner(Boolean(userState.isLoaded && authState.isLoaded), resolvedUserId);
  }, [userState.isLoaded, authState.isLoaded, userState.user?.id, authState.userId]);

  const signOut: ClerkResult["signOut"] = useCallback(
    async (...args: Parameters<ClerkResult["signOut"]>) => {
      syncActiveAuthOwner(true, null);
      clearClientSessionCaches();
      return clerkSignOut(...(args as [Parameters<ClerkResult["signOut"]>[0]]));
    },
    [clerkSignOut]
  ) as ClerkResult["signOut"];

  return (
    <AppAuthContext.Provider
      value={{
        clerkEnabled: true,
        userState,
        authState,
        signOut,
      }}
    >
      {children}
    </AppAuthContext.Provider>
  );
}

function E2EAuthBridge({ userId, children }: { userId: string; children: React.ReactNode }) {
  useEffect(() => {
    syncActiveAuthOwner(true, userId);
  }, [userId]);

  const e2eUserState = {
    isLoaded: true,
    isSignedIn: true,
    user: {
      id: userId,
      fullName: "E2E Test User",
      firstName: "E2E",
      primaryEmailAddress: { emailAddress: "e2e@example.com" },
    },
  } as unknown as UserResult;

  const e2eAuthState = {
    ...FALLBACK_AUTH_STATE,
    isLoaded: true,
    isSignedIn: true,
    userId,
  } as unknown as AuthResult;

  return (
    <AppAuthContext.Provider
      value={{
        clerkEnabled: false,
        userState: e2eUserState,
        authState: e2eAuthState,
        signOut: (async () => {}) as unknown as ClerkResult["signOut"],
      }}
    >
      {children}
    </AppAuthContext.Provider>
  );
}

/**
 * Provedor unificado de estado de autenticação no cliente.
 */
export function AppAuthProvider({
  clerkEnabled,
  e2eUserId = null,
  children,
}: {
  clerkEnabled: boolean;
  e2eUserId?: string | null;
  children: React.ReactNode;
}) {
  if (e2eUserId) {
    return <E2EAuthBridge userId={e2eUserId}>{children}</E2EAuthBridge>;
  }
  if (!clerkEnabled) {
    return (
      <AppAuthContext.Provider value={FALLBACK_CONTEXT_VALUE}>
        {children}
      </AppAuthContext.Provider>
    );
  }
  return <ClerkAuthBridge>{children}</ClerkAuthBridge>;
}

/** Substituto seguro para `useUser()`. */
export function useAppUser(): UserResult {
  return useContext(AppAuthContext).userState;
}

/** Substituto seguro para `useAuth()`. */
export function useAppAuth(): AuthResult {
  return useContext(AppAuthContext).authState;
}

/** Substituto seguro para `useClerk()`. */
export function useAppClerk(): { signOut: ClerkResult["signOut"]; clerkEnabled: boolean } {
  const ctx = useContext(AppAuthContext);
  return { signOut: ctx.signOut, clerkEnabled: ctx.clerkEnabled };
}

/** Indica se o provedor Clerk está montado na árvore atual. */
export function useIsClerkEnabled(): boolean {
  return useContext(AppAuthContext).clerkEnabled;
}
