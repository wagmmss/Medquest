import { test, expect } from "@playwright/test";

function makeSummary(overrides: {
  todayMode?: string;
  todaySource?: string;
  todayGoal?: number;
  marchaId?: "4_sprint" | "3_normal" | "2_pesada" | "1_sobrevivencia";
  marchaSource?: "confirmada" | "sugerida";
} = {}) {
  const mode = overrides.todayMode ?? "integral";
  const source = overrides.todaySource ?? "pattern";
  const goal = overrides.todayGoal ?? 25;
  const marchaId = overrides.marchaId ?? "3_normal";
  const marchaSource = overrides.marchaSource ?? "sugerida";
  return {
    today: {
      date_iso: "2027-02-04",
      mode,
      source,
      shifts: [],
      is_pos_plantao: mode === "pos_plantao",
      goal_questions: goal,
      reviews_optional: goal === 0,
      rodizio_id: "cirurgia",
      marcha_id: marchaId,
      marcha_source: marchaSource,
      guidance:
        mode === "pos_plantao"
          ? "Descanso pós-plantão. Meta zero; revisões opcionais."
          : "Dia integral no hospital.",
    },
    plan: {
      routine_mode_enabled: true,
      enamed_concept: 5,
      foco_override: {},
      ritual_done: {},
      has_feed_token: false,
      feed_token_created_at: null,
    },
    rodizio: {
      id: "cirurgia",
      label: "Cirurgia Geral",
      start: "2027-01-25",
      end: "2027-02-21",
      area: "Cirurgia",
      ancora70: "Abdome agudo e trauma",
      trilha30: "Clínica Médica",
      ancora_areas: ["Cirurgia"],
      procedimentos_alvo: ["Sutura simples"],
      micro_habito: "Revisar prescrição cirúrgica",
      week_pattern: null,
      foco_effective: {
        ancora70: "Abdome agudo e trauma",
        trilha30: "Clínica Médica",
        is_override: false,
      },
      next: { id: "anestesio_cti", label: "Anestesio & CTI", start: "2027-02-22", end: "2027-03-21" },
    },
    next_rodizio: {
      id: "anestesio_cti",
      label: "Anestesio & CTI",
      start: "2027-02-22",
      end: "2027-03-21",
    },
    week: {
      week_iso: "2027-02-01",
      marcha_id: marchaId,
      marcha_source: marchaSource,
      suggested_marcha_id: "3_normal",
      shift_weight: 0,
      weekly_goal: 205,
      semana_pesada: marchaId === "2_pesada" || marchaId === "1_sobrevivencia",
    },
    days: [],
    balance_7030: {
      total: 40,
      anchor: 28,
      anchor_pct: 70,
      other: 12,
      other_pct: 30,
      target_anchor_pct: 70,
      anchor_areas: ["Cirurgia"],
      window_from: "2027-01-29",
      window_to: "2027-02-04",
    },
    ritual: { cycle_key: "2027-01-30", done: {} },
    ferias: { current_week_id: null },
    curriculum_entries: {},
    milestones: [
      {
        id: "ms_1",
        titulo: "Prova USP-SP R1",
        data_iso: "2027-11-15",
        categoria: "prova",
        done: false,
        note: "",
        updated_at: "2027-02-01T00:00:00Z",
      },
    ],
    next_milestone: {
      id: "ms_1",
      titulo: "Prova USP-SP R1",
      data_iso: "2027-11-15",
      categoria: "prova",
      days_left: 284,
    },
  };
}

function makeFebPreview(nightShiftDates: Set<string>) {
  const days = [];
  for (let d = 1; d <= 28; d++) {
    const iso = `2027-02-${String(d).padStart(2, "0")}`;
    const prevIso = d > 1 ? `2027-02-${String(d - 1).padStart(2, "0")}` : "";
    const hasShift = nightShiftDates.has(iso);
    const isPos = prevIso ? nightShiftDates.has(prevIso) : false;
    const mode = isPos ? "pos_plantao" : hasShift ? "entrada_noturno" : "integral";
    days.push({
      date_iso: iso,
      mode,
      source: isPos ? "pos_plantao" : hasShift ? "shift" : "pattern",
      shifts: hasShift ? ["plantao_noturno"] : [],
      is_pos_plantao: isPos,
      goal_questions: isPos ? 0 : hasShift ? 10 : 25,
      reviews_optional: isPos,
      rodizio_id: "cirurgia",
      marcha_id: "3_normal",
      marcha_source: "sugerida",
      guidance: isPos ? "Descanso pós-plantão." : "Dia regular.",
    });
  }
  return { days, weeks: [] };
}

test.describe("PR 2 Central 6º Ano & R1 Frontend", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("medquest_onboarding_v1", "done"));
  });

  test("tabs navigate via click, keyboard and ?tab=, and render without planner configured", async ({
    page,
  }) => {
    const nightShifts = new Set<string>();
    const batchPayloads: Array<{ add?: Array<{ date_iso: string; kind: string }> }> = [];

    await page.route("**/api/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();

      if (url.includes("/api/auth/me")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "user_e2e_test",
            email: "e2e@example.com",
            is_curator: false,
            can_access_lessons: false,
          }),
        });
      }
      // Planner NÃO configurado (retorna config sem exam_date/start_date)
      if (url.includes("/api/planner/config")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
      }
      if (url.includes("/api/six-year/summary")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(makeSummary()),
        });
      }
      if (url.includes("/api/six-year/preview")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(makeFebPreview(nightShifts)),
        });
      }
      if (url.includes("/api/six-year/shifts/batch") && method === "POST") {
        const body = route.request().postDataJSON();
        batchPayloads.push(body);
        for (const item of body.add ?? []) {
          nightShifts.add(item.date_iso);
        }
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ added: (body.add ?? []).length, removed: 0, days: [] }),
        });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
    });

    // Abrir direto em ?tab=plano-6ano sem planner configurado
    await page.goto("/planner?tab=plano-6ano");
    await expect(page.getByRole("tab", { name: "Plano 6º Ano" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    await expect(page.getByRole("heading", { name: /Rodízio vigente: Cirurgia Geral/i })).toBeVisible();

    // Cadastrar plantão noturno em 2027-02-10 -> dia 2027-02-11 vira pos_plantao
    await page.locator('button[data-date-iso="2027-02-10"]').click();
    await expect(page.getByTestId("shift-day-popover")).toBeVisible();
    await page.getByRole("button", { name: /\+ Plantão noturno/i }).click();
    await expect(page.locator('button[data-date-iso="2027-02-11"]')).toHaveAttribute(
      "data-day-mode",
      "pos_plantao"
    );

    // Colar 3 datas -> preview mostra 3 -> confirmar chama shifts/batch com 3 itens
    await page.getByRole("button", { name: /Colar datas/i }).click();
    await page
      .getByLabel("Datas de plantão para importar")
      .fill("12/02/2027, 15/02/2027, 2027-02-20");
    await expect(page.getByText(/Confirmar lote \(3\)/)).toBeVisible();
    await page.getByRole("button", { name: /Confirmar lote \(3\)/ }).click();
    await expect.poll(() => batchPayloads.at(-1)?.add?.length).toBe(3);

    // Trocar para aba R1 & Currículo via clique e verificar renderização sem planner
    await page.getByRole("tab", { name: "R1 & Currículo" }).click();
    await expect(page).toHaveURL(/tab=r1/);
    await expect(page.getByRole("heading", { name: /Linha do Tempo de Marcos R1/i })).toBeVisible();
    await expect(page.getByText("Prova USP-SP R1")).toBeVisible();

    // Navegação por teclado (ArrowLeft volta para Plano 6º Ano)
    await page.getByRole("tab", { name: "R1 & Currículo" }).press("ArrowLeft");
    await expect(page.getByRole("tab", { name: "Plano 6º Ano" })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    // Verificar layout responsivo em 375px sem overflow horizontal
    await page.setViewportSize({ width: 375, height: 812 });
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
    );
    expect(hasOverflow).toBe(false);
  });

  test("Dashboard widget triggers 1-click Pós-plantão (daily_target -> 0) and Marcha change", async ({
    page,
  }) => {
    let isPosPlantao = false;
    let currentMarcha: "4_sprint" | "3_normal" | "2_pesada" | "1_sobrevivencia" = "3_normal";
    let overridePutCalled = false;
    let marchaPutCalled = false;

    await page.route("**/api/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();

      if (url.includes("/api/auth/me")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "user_e2e_test",
            email: "e2e@example.com",
            is_curator: false,
            can_access_lessons: false,
          }),
        });
      }
      if (url.includes("/api/six-year/day-override/2027-02-04") && method === "PUT") {
        overridePutCalled = true;
        isPosPlantao = true;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            day: makeSummary({ todayMode: "pos_plantao", todaySource: "override", todayGoal: 0 }).today,
          }),
        });
      }
      if (url.includes("/api/six-year/marcha/2027-02-01") && method === "PUT") {
        marchaPutCalled = true;
        const body = route.request().postDataJSON();
        currentMarcha = body.marcha_id;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            week_iso: "2027-02-01",
            marcha_id: currentMarcha,
            marcha_source: "confirmada",
          }),
        });
      }
      if (url.includes("/api/six-year/summary")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            makeSummary({
              todayMode: isPosPlantao ? "pos_plantao" : "integral",
              todaySource: isPosPlantao ? "override" : "pattern",
              todayGoal: isPosPlantao ? 0 : 25,
              marchaId: currentMarcha,
              marchaSource: marchaPutCalled ? "confirmada" : "sugerida",
            })
          ),
        });
      }
      if (url.includes("/api/dashboard/summary")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            stats: {
              total_questions: 100,
              distinct_answered: 10,
              total_attempts: 10,
              accuracy_all_attempts: 0.8,
              accuracy_latest_attempt: 0.8,
              coverage_pct: 0.1,
              srs_due_count: 0,
              accuracy_last7: 0.8,
              accuracy_prev7: 0.75,
              streak_days: 3,
              today_answered: 0,
              daily_target: isPosPlantao ? 0 : 25,
            },
            benchmark: null,
            bottlenecks: [],
            domain_summary: null,
            error_notebook: null,
            planner: { config: {}, progress: {}, topic_progress: {} },
          }),
        });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
    });

    await page.goto("/");
    const card = page.getByTestId("six-year-status-card");
    await expect(card).toBeVisible();
    await expect(card.getByText(/Integral · 25q/)).toBeVisible();

    // 1-clique Pós-plantão -> chama PUT e atualiza meta para 0q
    await card.getByRole("button", { name: "Hoje: Pós-plantão" }).click();
    await expect.poll(() => overridePutCalled).toBe(true);
    await expect(card.getByText(/Pós-plantão · 0q/)).toBeVisible();

    // Trocar Marcha pelo chip
    await card.getByRole("button", { name: /Marcha:/i }).click();
    await card.getByRole("menuitem", { name: /Pesada/i }).click();
    await expect.poll(() => marchaPutCalled).toBe(true);
    await expect(card.getByRole("button", { name: /Marcha: Pesada \(confirmada\)/i })).toBeVisible();
  });
});
