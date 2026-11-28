import { test, expect } from "@playwright/test";

test.describe("PR 0 Auth Lockdown", () => {
  test("authenticated E2E shell renders dashboard without demo banner or guest button", async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      const url = route.request().url();
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
      if (url.includes("/api/dashboard/summary")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            overview: {
              total_attempts: 0,
              accuracy: 0,
              streak_days: 0,
              today_answered: 0,
              daily_target: 30,
              reviews_due: 0,
              total_questions_db: 100,
              answered_unique: 0,
            },
            learning_profile: {
              generated_at: "2026-11-27T00:00:00Z",
              goal: {
                questions_today: 30,
                configured_daily_questions: 30,
                reviews_due: 0,
                reviews_to_do_today: 0,
                backlog_pending: 0,
                hours_budget: 4,
                max_capacity: 80,
              },
              topics: [],
            },
            timeline: [],
            weak_topics: [],
            at_risk_topics: [],
            recommendations: [],
          }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await page.goto("/");
    await expect(page.locator("#conteudo-principal")).toBeVisible();
    await expect(page.getByText(/Modo Demonstração/i)).toHaveCount(0);
    await expect(page.getByText(/Explorar Modo Demonstração/i)).toHaveCount(0);
  });

  test("displays clear restricted-access overlay when API returns 403 ACCESS_RESTRICTED", async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      return route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ error: "Forbidden", code: "ACCESS_RESTRICTED" }),
      });
    });

    await page.goto("/");
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Acesso restrito")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Sair e trocar de conta/i })).toBeVisible();
  });
});
