import { expect, test, type Page } from "@playwright/test";

// The PLAN.md section 3 demo, end to end, in mock mode. Screenshots go to $SHOTS_DIR when it is set.
const SHOTS = process.env.SHOTS_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

async function waitForBatch(page: Page, status = "completed") {
  await expect(page.getByTestId("batch-progress")).toHaveAttribute("data-status", status, { timeout: 60_000 });
}

test("demo flow: close, inspect, approve, export, replay, admin", async ({ page }) => {
  await page.goto("/login?mockReset=1");
  await expect(page.getByTestId("demo-login-reviewer")).toBeVisible();
  await shot(page, "e2e-01-login");

  // Preparer starts the close
  await page.getByTestId("demo-login-preparer").click();
  await expect(page.getByTestId("current-user-role")).toHaveAttribute("data-role", "preparer");
  await expect(page.getByTestId("empty-batch")).toBeVisible();
  await page.getByTestId("close-period-button").click();
  await expect(page.getByTestId("client-tile-blue-harbor-coffee")).toHaveAttribute("data-status", /queued|running/);
  await waitForBatch(page);
  await expect(page.getByTestId("client-tile-blue-harbor-coffee")).toHaveAttribute("data-recon", "reconciled");
  await expect(page.getByTestId("client-tile-cedar-ridge-landscaping")).toHaveAttribute("data-recon", "needs_review");
  await expect(page.getByTestId("ground-truth")).toBeVisible();
  await shot(page, "e2e-02-dashboard");

  // Run detail
  await page.getByTestId("client-tile-blue-harbor-coffee").click();
  await expect(page.getByTestId("run-header")).toBeVisible();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-recon", "reconciled");
  await expect(page.getByTestId("timeline-step-3")).toBeVisible();
  await expect(page.locator('[data-testid="matching-view"][data-state="ready"]')).toBeVisible();
  await expect(page.getByTestId("recon-summary")).toHaveAttribute("data-difference", "0.00");
  await expect(page.getByTestId("blast-radius")).toHaveAttribute("data-state", "ready");
  await expect(page.getByTestId("untrusted-text-callout")).toContainText("Treated as data");
  await expect(page.getByTestId("download-ajes")).toBeDisabled();
  await page.getByTestId("tab-exceptions").click();
  await page.getByTestId("tab-ajes").click();
  await page.getByTestId("tab-workpaper").click();
  await page.getByTestId("tab-memo").click();
  await shot(page, "e2e-03-run");

  // Reviewer approves (maker-checker allows it: a different user started the close)
  await page.getByTestId("user-menu").click();
  await page.getByTestId("role-switch-reviewer").click();
  await expect(page.getByTestId("current-user-role")).toHaveAttribute("data-role", "reviewer");
  await page.getByTestId("approve-comment").fill("Checked the NSF and transposition entries. OK to post.");
  await page.getByTestId("approve-button").click();
  await expect(page.getByTestId("approval-banner")).toContainText("Approved by Jordan Lee");
  await expect(page.getByTestId("download-ajes")).toBeEnabled();
  const download = page.waitForEvent("download");
  await page.getByTestId("download-ajes").click();
  expect((await download).suggestedFilename()).toContain("ajes.csv");
  await shot(page, "e2e-04-approved");

  // Replay: fresh sandbox, same code, same inputs, same hashes
  await page.getByTestId("replay-button").click();
  await expect(page.getByTestId("reproducible-badge")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("replay-result")).toHaveAttribute("data-match", "true");
  await shot(page, "e2e-05-replay");
  await page.keyboard.press("Escape");

  // Admin and the containment story
  await page.getByTestId("user-menu").click();
  await page.getByTestId("role-switch-admin").click();
  await page.getByTestId("nav-admin").click();
  await expect(page.getByTestId("kill-switch")).toBeVisible();
  await expect(page.getByTestId("audit-chain")).toContainText("Chain verified");
  await shot(page, "e2e-06-admin");
  await page.getByTestId("nav-how").click();
  await expect(page.getByTestId("architecture-diagram")).toBeVisible();
  await shot(page, "e2e-07-how");
});

test("maker-checker, kill switch and re-run", async ({ page }) => {
  await page.goto("/login?mockReset=1");
  await page.getByTestId("demo-login-admin").click();
  await page.getByTestId("close-period-button").click();
  await expect(page.getByTestId("client-tile-alder-finch-law")).toHaveAttribute("data-status", "running", { timeout: 15_000 });

  // Kill switch stops the close and blocks new work
  await page.getByTestId("nav-admin").click();
  await page.getByTestId("kill-switch").click();
  await page.getByTestId("kill-switch-confirm").click();
  await expect(page.getByTestId("kill-switch-card")).toHaveAttribute("data-on", "true");
  await expect(page.getByTestId("kill-switch-auto-resume")).toBeVisible();
  await page.getByTestId("nav-close").click();
  await expect(page.getByTestId("kill-switch-banner")).toBeVisible();
  await expect(page.getByTestId("close-period-button")).toBeDisabled();

  // Release it, re-run one stopped client
  await page.getByTestId("nav-admin").click();
  await page.getByTestId("kill-switch").click();
  await expect(page.getByTestId("kill-switch-card")).toHaveAttribute("data-on", "false");
  await page.getByTestId("nav-close").click();
  const stopped = page.locator('[data-testid^="client-tile-"][data-status="stopped"]').first();
  const id = await stopped.getAttribute("data-testid");
  await stopped.getByTestId("rerun-button").click();
  await expect(page.getByTestId(id as string)).toHaveAttribute("data-status", /queued|running|succeeded/);
  await waitForBatch(page, "stopped");

  // Maker-checker: the admin started this close, so the admin cannot approve the re-run
  await page.getByTestId(id as string).click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "succeeded", { timeout: 30_000 });
  await expect(page.getByTestId("cannot-approve-reason")).toContainText("Maker-checker");
});
