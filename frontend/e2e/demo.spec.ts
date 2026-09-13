import { expect, test, type Page } from "@playwright/test";

// The presenter flow against a running deployment (see playwright.config.ts for the base URL).
// Each step waits on the real pipeline and, when a key is configured, live Claude narration.

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "page must not scroll horizontally").toBeLessThanOrEqual(0);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByText("You're looking at #spend-signals")).toBeVisible();
});

test("three presenter steps, the ask, and the month-end carry-over", async ({ page }) => {
  // 1. history -> a report with the two quiet items and nothing to alert on
  await page.getByRole("button", { name: "Load history" }).click();
  await expect(page.getByText(/^(First look|Monthly report) · /)).toBeVisible();
  await expect(page.getByText("Nothing needs attention")).toBeVisible();
  await expect(page.getByText("Loom", { exact: true })).toBeVisible();
  await expect(page.getByText("Notion", { exact: true })).toBeVisible();
  await expect(page.getByText("Vanta", { exact: true })).toHaveCount(0);
  await noHorizontalOverflow(page);

  // 2. new charges -> Anthropic off its trend, Pinecone new, with the cost-type question
  await page.getByRole("button", { name: "New charges" }).click();
  await expect(page.getByText(/Anthropic is running well above its trend|Anthropic.*above its trend/)).toBeVisible();
  await expect(page.getByText(/Pinecone Systems/).first()).toBeVisible();
  await expect(page.getByText("+$9.6K/mo").first()).toBeVisible();
  await expect(page.getByText("+$6.5K/mo").first()).toBeVisible();
  const question = page.getByText(/We're treating Pinecone Systems as/);
  await expect(question).toBeVisible();

  // Answer so that Pinecone ends up usage-based whatever the classifier said.
  const usageButton = page.getByRole("button", { name: "No, it's usage-based" });
  if (await usageButton.count()) await usageButton.click();
  else await page.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.getByText(/Pinecone Systems is treated as usage-based/)).toBeVisible();
  await expect(page.getByText(/We're treating Pinecone Systems as/)).toHaveCount(0);
  await noHorizontalOverflow(page);

  // 3. month closes -> both issues carried as open, renewal notice, no new alerts
  await page.getByRole("button", { name: "Month closes" }).click();
  await expect(page.getByText("Open since Sep 5")).toHaveCount(2);
  await expect(page.getByText(/Renewal coming up/)).toBeVisible();
  await expect(page.getByText(/Price change/).first()).toBeVisible();
  await noHorizontalOverflow(page);

  // 4. the transcript survives a reload
  await page.reload();
  await expect(page.getByText("Open since Sep 5")).toHaveCount(2);
  await expect(page.getByText(/^(First look|Monthly report) · /)).toHaveCount(2);
});

test("settings shows the override and reset clears the channel", async ({ page }) => {
  await page.getByRole("button", { name: "Load history" }).click();
  await expect(page.getByText(/^(First look|Monthly report) · /)).toBeVisible();
  await page.getByRole("button", { name: "New charges" }).click();
  const usageButton = page.getByRole("button", { name: "No, it's usage-based" });
  await expect(page.getByText(/We're treating Pinecone Systems as/)).toBeVisible();
  if (await usageButton.count()) await usageButton.click();
  else await page.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.getByText(/Pinecone Systems is treated as usage-based/)).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByText("Alert thresholds")).toBeVisible();
  await expect(page.getByText("Vendor classifications")).toBeVisible();
  const pineconeRow = page.getByRole("row", { name: /Pinecone Systems/ });
  await expect(pineconeRow.getByText("Override")).toBeVisible();

  // Reset is a two-click confirm.
  await page.getByRole("button", { name: "Reset demo", exact: true }).click();
  await page.getByRole("button", { name: "Yes, reset demo" }).click();
  await expect(page.getByText("You're looking at #spend-signals")).toBeVisible();
  await noHorizontalOverflow(page);
});
