import { test, expect, type Page } from "@playwright/test";

const TOKEN = "synthetic-ui-test-token-not-for-real-evidence-2026";

async function readJson(page: Page, path: string) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await page.request.get(path);
    if (response.status() === 429 && attempt < 4) {
      await page.waitForTimeout(250 * 2 ** attempt);
      continue;
    }
    expect(response.status()).toBe(200);
    return response.json();
  }
  throw new Error("bounded request retries exhausted");
}

test("evidence journey, mode labels, restored boundaries, comparison and logout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /The trace ends/ }),
  ).toBeVisible();
  await page.getByLabel("Investigator access token").fill(TOKEN);
  await page.getByRole("button", { name: "Open investigation" }).click();
  await expect(
    page.getByRole("heading", { name: "Follow the evidence." }),
  ).toBeVisible();
  const cookies = await page.context().cookies();
  expect(
    cookies.find((cookie) => cookie.name === "sentinel_session")?.httpOnly,
  ).toBe(true);
  const listing = await readJson(page, "/api/backend/v1/runs?limit=100");
  expect(listing.runs.length).toBe(12);
  const live = listing.runs.find(
    (run: { run_id: string }) => run.run_id === "isolated-branch",
  );
  await page.locator(`[data-run-id="${live.run_id}"]`).click();
  await expect(
    page.getByText("Protected materialization", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Provenance", exact: true }).click();
  await expect(page.getByLabel("Declared dependency graph")).toBeVisible();
  await page.getByRole("button", { name: "Replay lab", exact: true }).click();
  await page
    .getByRole("button", { name: "Restore and match boundaries" })
    .click();
  await expect(
    page.getByRole("heading", { name: "BOUNDARY_REPLAY_MATCHED" }),
  ).toBeVisible();
  await expect(
    page.getByText(/boundaries matched · 0 live calls/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await page.getByRole("button", { name: "Recheck stored evidence" }).click();
  await expect(page.getByRole("status")).toContainText(
    "verified_capsule_bytes",
  );
  const experiment = listing.runs.find((run: { run_id: string }) =>
    run.run_id.startsWith("experiment-"),
  );
  await page.locator(`[data-run-id="${experiment.run_id}"]`).click();
  await expect(
    page.getByRole("heading", { name: "One checkpoint. Three policies." }),
  ).toBeVisible();
  await expect(
    page.getByText("PARETO FRONTIER", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody")).toContainText("deny protected");
  await expect(page.getByLabel("Verified policy source")).toBeVisible();
  await expect(page.locator(".monaco-editor")).toBeVisible();
  await page
    .getByRole("button", {
      name: "Inspect protected export / allow both",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Protected materialization", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Replay lab", exact: true }).click();
  await page
    .getByRole("button", { name: "Restore and match boundaries" })
    .click();
  await expect(
    page.getByRole("heading", { name: "BOUNDARY_REPLAY_MATCHED" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to comparison" }).click();
  await page.getByRole("button", { name: "World diff", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "What changed in the covered world?" }),
  ).toBeVisible();
  await expect(
    page.getByText("∆ outbox/leak.txt", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: "../.local-controller/ui-validation/investigation-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../.local-controller/ui-validation/investigation-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  const pack = listing.runs.find((run: { run_id: string }) =>
    run.run_id.startsWith("pack-"),
  );
  await page.locator(`[data-run-id="${pack.run_id}"]`).click();
  await page.getByRole("button", { name: "Replay lab", exact: true }).click();
  await page
    .getByRole("button", { name: "Restore and match boundaries" })
    .click();
  await expect(
    page.getByRole("heading", { name: "VERIFIED_REPLAY", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/finite environment pack's declared file effects/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Lock workspace" }).click();
  await expect(
    page.getByRole("heading", { name: /The trace ends/ }),
  ).toBeVisible();
  expect((await page.request.get("/api/backend/v1/runs")).status()).toBe(401);
  expect(errors).toEqual([]);
});

test("session rejects missing origin and invalid credentials", async ({
  page,
}) => {
  await page.goto("/");
  const rejected = await page.request.post("/api/session", {
    data: { token: TOKEN },
  });
  expect(rejected.status()).toBe(403);
  await page
    .getByLabel("Investigator access token")
    .fill("incorrect-synthetic-token-with-enough-characters");
  await page.getByRole("button", { name: "Open investigation" }).click();
  await expect(page.getByText("Access denied", { exact: true })).toBeVisible();
  expect((await page.request.get("/api/backend/v1/runs")).status()).toBe(401);
});

test("recorded operation stream localizes a real restored file effect", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Investigator access token").fill(TOKEN);
  await page.getByRole("button", { name: "Open investigation" }).click();
  await expect(
    page.getByRole("heading", { name: "Follow the evidence." }),
  ).toBeVisible();
  const listing = await readJson(page, "/api/backend/v1/runs?limit=100");
  const pack = listing.runs.find((run: { run_id: string }) =>
    run.run_id.startsWith("pack-"),
  );
  await page.locator(`[data-run-id="${pack.run_id}"]`).click();
  await page.getByRole("button", { name: "Replay lab", exact: true }).click();
  await page.getByLabel("Predicate file basename").fill("out.txt");
  await page
    .getByRole("button", { name: "Localize file creation", exact: true })
    .click();
  const console = page.getByLabel("Bounded forensic operations");
  await expect(console.locator("pre")).toContainText('"first_true_prefix": 2');
  await expect(console.locator("pre")).toContainText(
    '"mode": "VERIFIED_REPLAY"',
  );
  await expect(console.getByText(/bisect · completed/)).toBeVisible();
  const jobs = await readJson(page, `/api/backend/v1/runs/${pack.run_id}/jobs`);
  expect(jobs.jobs[0].state).toBe("completed");
  const result = await readJson(
    page,
    `/api/backend/v1/runs/${pack.run_id}/jobs/${jobs.jobs[0].job_id}/result`,
  );
  expect(result.report.first_true_prefix).toBe(2);
  expect(
    result.report.probes.every(
      (probe: { replay: { live_nondeterministic_calls: number } }) =>
        probe.replay.live_nondeterministic_calls === 0,
    ),
  ).toBe(true);
});
