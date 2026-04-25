import { expect, test } from "@playwright/test";

test("operator can create a project and run a mock stage", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Studio piosenek i klipów AI" })).toBeVisible();
  await expect(page.getByText("Mock GPU server is ready for local development.")).toBeVisible();

  await page.getByLabel("Tytuł projektu").fill("Szczoteczka bohater");
  await page.getByLabel("Temat").fill("mycie zębów");
  await page.getByLabel("Wiek").fill("3-5");
  await page.getByLabel("Emocja").fill("radość");
  await page.getByLabel("Cel edukacyjny").fill("dziecko pamięta o porannym myciu zębów");
  await page.getByLabel("Postacie").fill("toothbrush_friend_v1");
  await page.getByRole("button", { name: "Utwórz projekt" }).click();

  await expect(page.getByTestId("selected-project-title")).toContainText("Szczoteczka bohater");
  await page.getByTestId("run-lyrics-button").click();
  await expect(page.getByText("Mock job for lyrics.generate finished locally.")).toBeVisible();
  await expect(page.getByTestId("stage-lyrics.generate")).toContainText("do akceptacji");
});
