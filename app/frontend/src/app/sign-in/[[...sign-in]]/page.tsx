import { SignIn } from "@clerk/nextjs";
import { ClinicalIcon } from "@/components/ui/ClinicalIcon";

interface SignInPageProps {
  searchParams: Promise<{ redirect_url?: string | string[] }>;
}

function resolveSafeRedirectUrl(raw: string | string[] | undefined): string {
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  if (!candidate || typeof candidate !== "string") return "/";
  const trimmed = candidate.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//") || trimmed.startsWith("/sign-in")) {
    return "/";
  }
  return trimmed;
}

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const params = await searchParams;
  const redirectUrl = resolveSafeRedirectUrl(params.redirect_url);

  return (
    <div className="flex w-full min-h-screen items-center justify-center p-6 bg-background overflow-y-auto">
      <div className="flex flex-col items-center max-w-md w-full bg-surface p-6 sm:p-8 rounded-sm border border-line-subtle shadow-lg">
        <div className="w-12 h-12 bg-ink-primary text-surface rounded-xs flex items-center justify-center mb-4 shadow-2xs">
          <ClinicalIcon name="local_hospital" className="w-6 h-6 text-canvas" strokeWidth={2.2} />
        </div>
        <h1 className="text-xl font-bold text-ink-primary text-center mb-1">
          MedQuest Clinical Workspace
        </h1>
        <p className="text-ink-secondary text-center mb-6 text-xs">
          Acesso restrito. Entre com sua conta autorizada para continuar.
        </p>
        <div className="w-full flex justify-center">
          <SignIn
            routing="path"
            path="/sign-in"
            fallbackRedirectUrl={redirectUrl}
            forceRedirectUrl={redirectUrl}
          />
        </div>
      </div>
    </div>
  );
}
