import { expect, test } from "@playwright/test";

test("operator can create a project and run a mock stage", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Studio piosenek i klipów AI" })).toBeVisible();
  await expect(page.getByText("Mock GPU server is ready for local development.")).toBeVisible();

  await page.getByLabel("Nazwa profilu").fill("GPU tower draft");
  await page.getByLabel("Host").fill("gpu-studio.tailnet.local");
  await page.getByLabel("Użytkownik SSH").fill("studio");
  await page.getByLabel("Port").fill("22");
  await page.getByLabel("Remote root").fill("/srv/ai-kids-studio");
  await page.getByLabel("Ścieżka klucza").fill("~/.ssh/ai_kids_studio");
  await page.getByLabel("Tailscale").fill("gpu-studio");
  await page.getByRole("button", { name: "Zapisz profil" }).click();
  await expect(page.getByText("Mock GPU server profile 'GPU tower draft' is ready for local development.")).toBeVisible();

  await page.getByLabel("Tytuł projektu").fill("Szczoteczka bohater");
  await page.getByLabel("Temat").fill("mycie zębów");
  await page.getByLabel("Wiek").fill("3-5");
  await page.getByLabel("Emocja").fill("radość");
  await page.getByLabel("Cel edukacyjny").fill("dziecko pamięta o porannym myciu zębów");
  await page.getByLabel("Postacie").fill("toothbrush_friend_v1");
  await page.getByRole("button", { name: "Utwórz projekt" }).click();

  await expect(page.getByTestId("selected-project-title")).toContainText("Szczoteczka bohater");
  await expect(page.getByTestId("run-lyrics-button")).toBeDisabled();
  await page.getByTestId("approve-brief.generate").click();
  await expect(page.getByTestId("stage-brief.generate")).toContainText("gotowe");
  await expect(page.getByText("Brief zatwierdzony.")).toBeVisible();
  await expect(page.getByTestId("run-lyrics-button")).toBeEnabled();

  await page.getByTestId("run-lyrics-button").click();
  await expect(page.getByText("Mock job for lyrics.generate finished locally.")).toBeVisible();
  await expect(page.getByTestId("lyrics-artifact")).toContainText("Refren");
  await expect(page.getByTestId("lyrics-artifact")).toContainText("Mycie zębów");
  await expect(page.getByTestId("stage-lyrics.generate")).toContainText("do akceptacji");
  await page.getByTestId("approve-lyrics.generate").click();
  await expect(page.getByTestId("stage-lyrics.generate")).toContainText("gotowe");
  await expect(page.getByText("Tekst zatwierdzony.")).toBeVisible();
});
