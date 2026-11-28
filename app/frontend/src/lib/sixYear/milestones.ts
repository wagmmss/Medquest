// Contagem regressiva pura para marcos do R1.

export type MilestoneCategory = "curriculo" | "estudo" | "graduacao" | "prova" | "ingresso";

export interface MilestoneLike {
  id: string;
  titulo: string;
  data_iso: string;
  categoria: MilestoneCategory;
  done?: boolean;
  note?: string;
}

export interface MilestoneCountdown {
  milestone: MilestoneLike;
  daysLeft: number;
  weeksLeft: number;
  monthsApprox: number;
  status: "overdue" | "soon" | "upcoming";
  label: string;
}

export function computeMilestoneCountdown(
  milestone: MilestoneLike,
  nowDate: Date = new Date()
): MilestoneCountdown {
  const [y, m, d] = String(milestone.data_iso || "").split("-").map(Number);
  if (!y || !m || !d) {
    return {
      milestone,
      daysLeft: 0,
      weeksLeft: 0,
      monthsApprox: 0,
      status: "upcoming",
      label: "Data inválida",
    };
  }
  const todayUtc = Date.UTC(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate());
  const targetUtc = Date.UTC(y, m - 1, d);
  const diffDays = Math.round((targetUtc - todayUtc) / 86400000);
  const weeksLeft = Math.floor(Math.abs(diffDays) / 7);
  const monthsApprox = Number((Math.abs(diffDays) / 30.4375).toFixed(1));

  if (diffDays < 0) {
    return {
      milestone,
      daysLeft: diffDays,
      weeksLeft,
      monthsApprox,
      status: "overdue",
      label: `Passou há ${Math.abs(diffDays)} dia(s)`,
    };
  }
  if (diffDays === 0) {
    return {
      milestone,
      daysLeft: 0,
      weeksLeft: 0,
      monthsApprox: 0,
      status: "soon",
      label: "Hoje",
    };
  }
  const status: MilestoneCountdown["status"] = diffDays <= 60 ? "soon" : "upcoming";
  const label =
    diffDays >= 60
      ? `Faltam ${diffDays} dias (${monthsApprox} meses)`
      : `Faltam ${diffDays} dias (${weeksLeft} sem)`;
  return {
    milestone,
    daysLeft: diffDays,
    weeksLeft,
    monthsApprox,
    status,
    label,
  };
}
