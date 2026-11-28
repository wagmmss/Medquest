import { PlannerShell, type PlannerTabId } from "./PlannerShell";
import type { PlannerOrganizationMode } from "@/types/api";

function resolveTab(raw?: string): PlannerTabId {
  if (raw === "plano-6ano" || raw === "r1" || raw === "cronograma") {
    return raw;
  }
  return "cronograma";
}

export default async function PlannerPage({
  searchParams,
}: {
  searchParams: Promise<{ intensive?: string; org?: string; tab?: string }>;
}) {
  const sp = await searchParams;
  const isIntensive = sp.intensive === "true";
  const orgParam: PlannerOrganizationMode | undefined =
    sp.org === "internato" ? "internato" : sp.org === "geral" ? "geral" : undefined;
  const initialTab = resolveTab(sp.tab);

  return (
    <PlannerShell
      isIntensive={isIntensive}
      initialOrganization={orgParam}
      initialTab={initialTab}
    />
  );
}
