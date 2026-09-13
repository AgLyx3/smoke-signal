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

  // 2b. a clarifying question in the thread under the Anthropic alert, answered from its evidence
  await page.getByRole("button", { name: "Reply in thread", exact: true }).first().click(); // the Anthropic card's button
  const thread = page.getByRole("complementary", { name: "Thread" });
  await expect(thread.getByText("Anthropic", { exact: true })).toBeVisible();
  await thread.getByRole("button", { name: "Show me the charges" }).click();
  const botTurn = thread.getByTestId("thread-bot-turn").first();
  await expect(botTurn).toBeVisible({ timeout: 90_000 });
  await expect(botTurn).toContainText(/34,6|34\.6K|Anthropic/);
  await expect(botTurn.getByText(/via Claude|template answer/)).toBeVisible();
  await expect(page.getByRole("button", { name: /1 reply/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: /1 reply/ })).toBeVisible(); // thread persists
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

  // Connections: a provider key keeps only its masked tail; runway framing has its own destination.
  await expect(page.getByText("Connections", { exact: true })).toBeVisible();
  await page.getByLabel("Anthropic admin key").fill("sk-ant-demo-not-a-real-key-000000001234");
  await page.getByRole("button", { name: "Connect" }).first().click();
  await expect(page.getByText("••••1234")).toBeVisible();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  const stored = await page.evaluate(() => localStorage.getItem("smoke-signal:connections") ?? "");
  expect(stored).toContain("1234");
  expect(stored).not.toContain("sk-ant-demo"); // the key itself is never stored
  await page.getByRole("switch", { name: "Runway framing" }).click();
  await expect(page.getByRole("radio", { name: /Direct message to the founder/ })).toBeChecked();

  // Runway framing on, routed to the founder's DM: the channel stays dollars-only, the Cost
  // Signals direct message carries the cash position and the runway lines.
  await page.goto("/");
  await expect(page.getByTestId("runway-weeks")).toHaveCount(0);
  await expect(page.getByTestId("cash-position")).toHaveCount(0);
  await expect(page.getByTestId("runway-dm-hint").first()).toContainText("direct message to Dana K.");
  await expect(page.getByTestId("dm-unread")).toHaveText("2");
  await page.getByRole("button", { name: /^Smoke Signal/ }).click();
  const dmCash = page.getByTestId("cash-position").first();
  await expect(dmCash).toContainText(/Rho Treasury/);
  await expect(page.getByTestId("dm-runway")).toContainText(/weeks? of runway/);
  await expect(page.getByTestId("dm-unread")).toHaveCount(0);
  await noHorizontalOverflow(page);

  // Cash in gets the same ask: the $200K wire is asked about; "funding" removes it from net burn,
  // so runway drops and the question does not come back.
  const before = Number((await dmCash.textContent())?.match(/Runway\s+(\d+\.\d) months/)?.[1]);
  await expect(dmCash.getByTestId("inflow-ask")).toContainText("$200,000");
  await dmCash.getByRole("button", { name: "No, it's funding" }).click();
  await expect(dmCash.getByText(/is funding, not counted as cash in/)).toBeVisible({ timeout: 60_000 });
  await expect(dmCash.getByRole("button", { name: "No, it's funding" })).toHaveCount(0);
  // The re-run is async; poll until the cash card shows the recomputed runway.
  await expect
    .poll(async () => Number((await dmCash.textContent())?.match(/Runway\s+(\d+\.\d) months/)?.[1]), { timeout: 60_000 })
    .toBeLessThan(before);
  await page.getByRole("button", { name: "spend-signals" }).click();
  await expect(page.getByText(/Anthropic is running well above its trend/)).toBeVisible();

  // Routed to the channel instead: alerts state weeks of runway, reports carry the cash position.
  await page.goto("/settings");
  await page.getByRole("radio", { name: /#spend-signals channel/ }).check();
  await page.reload();
  await expect(page.getByText("••••1234")).toBeVisible();
  await expect(page.getByRole("radio", { name: /#spend-signals channel/ })).toBeChecked();
  await noHorizontalOverflow(page);
  await page.goto("/");
  await expect(page.getByTestId("runway-weeks").first()).toContainText(/weeks? of runway/);
  await expect(page.getByText("Runway detail → #spend-signals").first()).toBeVisible();
  const cash = page.getByTestId("cash-position").first();
  await expect(cash).toContainText(/Runway\s+\d+\.\d months/);
  await expect(cash).toContainText(/Rho Treasury/);
  await noHorizontalOverflow(page);
  await page.goto("/settings");

  // Reset is a two-click confirm.
  await page.getByRole("button", { name: "Reset demo", exact: true }).click();
  await page.getByRole("button", { name: "Yes, reset demo" }).click();
  await expect(page.getByText("You're looking at #spend-signals")).toBeVisible();
  await noHorizontalOverflow(page);
});
