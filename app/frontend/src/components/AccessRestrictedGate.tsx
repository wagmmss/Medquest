"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert, LogOut } from "lucide-react";
import { useAppClerk } from "@/lib/auth-client";

export const ACCESS_RESTRICTED_EVENT = "medquest-access-restricted";

export function AccessRestrictedGate() {
  const router = useRouter();
  const [restricted, setRestricted] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const { signOut, clerkEnabled } = useAppClerk();

  useEffect(() => {
    const onRestricted = () => setRestricted(true);
    window.addEventListener(ACCESS_RESTRICTED_EVENT, onRestricted);
    return () => window.removeEventListener(ACCESS_RESTRICTED_EVENT, onRestricted);
  }, []);

  if (!restricted) return null;

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      if (clerkEnabled) {
        await signOut({ redirectUrl: "/sign-in" });
      } else {
        router.push("/sign-in");
      }
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="access-restricted-title"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background/95 backdrop-blur-xs p-6"
    >
      <div className="w-full max-w-md rounded-sm border border-line-subtle bg-surface p-6 sm:p-8 shadow-xl text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-sm bg-destructive/15 text-destructive">
          <ShieldAlert className="h-6 w-6" aria-hidden="true" />
        </div>
        <h2 id="access-restricted-title" className="text-lg font-bold text-ink-primary mb-2">
          Acesso restrito
        </h2>
        <p className="text-sm text-ink-secondary mb-6">
          Esta conta não está autorizada a acessar este ambiente do MedQuest. Entre com a conta
          autorizada para continuar.
        </p>
        <button
          type="button"
          onClick={handleSignOut}
          disabled={signingOut}
          className="inline-flex items-center justify-center gap-2 rounded-sm bg-ink-primary px-4 py-2.5 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-60 cursor-pointer"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          <span>{signingOut ? "Saindo..." : "Sair e trocar de conta"}</span>
        </button>
      </div>
    </div>
  );
}
