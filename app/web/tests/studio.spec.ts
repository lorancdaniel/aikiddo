import { expect, test } from "@playwright/test";

test("operator sees a server-first generation cockpit", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Studio piosenek i klipów AI" })).toBeVisible();
  await expect(page.getByText("generowanie na serwerze")).toBeVisible();
  await expect(page.getByTestId("server-generation")).toContainText("Generacja serwerowa");
  await expect(page.getByTestId("server-generation")).toContainText("Zapisz profil serwera");
  await expect(page.getByText("Mock", { exact: false })).toHaveCount(0);
  await expect(page.getByText("mock", { exact: false })).toHaveCount(0);

  await page.getByLabel("Tytuł projektu").fill("Szczoteczka bohater");
  await page.getByLabel("Temat").fill("mycie zębów");
  await page.getByLabel("Wiek").fill("3-5");
  await page.getByLabel("Emocja").fill("radość");
  await page.getByLabel("Cel edukacyjny").fill("dziecko pamięta o porannym myciu zębów");
  await page.getByLabel("Postacie").fill("toothbrush_friend_v1");
  await page.getByRole("button", { name: "Utwórz projekt" }).click();

  await expect(page.getByTestId("selected-project-title")).toContainText("Szczoteczka bohater");
  await expect(page.getByTestId("server-generation").getByRole("button", { name: "Generuj na serwerze" })).toBeDisabled();
  await expect(page.getByTestId("run-lyrics-button")).toBeDisabled();

  await expect(page.getByLabel("Nazwa profilu")).toHaveValue("Production GPU worker");
  await expect(page.getByLabel("Użytkownik SSH")).toHaveValue("daniel");
  await expect(page.getByLabel("Remote root")).toHaveValue("/home/daniel/aikiddo-worker");
});
