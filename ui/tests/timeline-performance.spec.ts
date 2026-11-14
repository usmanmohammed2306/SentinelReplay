import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

for (const target of [3186, 50000]) {
  test(`${target}-boundary timeline becomes interactive after data arrival in25 fresh navigations`, async ({
    page,
  }) => {
    test.setTimeout(180000);
    await page.addInitScript(() => {
      const original = Response.prototype.json;
      Response.prototype.json = async function (...args) {
        const result = await original.apply(this, args);
        const measured = (
          window as unknown as { sentinelMeasuredRunId?: string }
        ).sentinelMeasuredRunId;
        if (
          measured &&
          this.url.includes(`/${measured}/`) &&
          /\/(timeline\?|incidents$)/.test(this.url)
        ) {
          (
            window as unknown as { sentinelDataArrival: number }
          ).sentinelDataArrival = performance.now();
        }
        return result;
      };
    });
    await page.goto("/");
    await page
      .getByLabel("Investigator access token")
      .fill("synthetic-ui-test-token-not-for-real-evidence-2026");
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(
      page.getByRole("heading", { name: "Follow the evidence." }),
    ).toBeVisible();
    // Discovery is outside the render measurement and observes the same admission
    // contract as the app. A previous test's request may still be draining.
    let response = await page.request.get("/api/backend/v1/runs?limit=100");
    for (let attempt = 0; response.status() === 429 && attempt < 4; attempt++) {
      await page.waitForTimeout(250 * 2 ** attempt);
      response = await page.request.get("/api/backend/v1/runs?limit=100");
    }
    expect(response.status()).toBe(200);
    const listing = await response.json();
    const run = listing.runs.find(
      (row: { records: number }) => row.records === target,
    );
    expect(run).toBeTruthy();
    await page.addInitScript((runId: string) => {
      (
        window as unknown as { sentinelMeasuredRunId: string }
      ).sentinelMeasuredRunId = runId;
    }, run.run_id);
    const samples: number[] = [];
    const navigationToData: number[] = [];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (let trial = 0; trial < 25; trial++) {
      await page.goto("/");
      const settled = page.waitForResponse((response) =>
        response.url().includes(`/${run.run_id}/phases`),
      );
      await page.locator(`[data-run-id="${run.run_id}"]`).click();
      const timeline = page.getByLabel("Boundary timeline", { exact: true });
      // Cold indexing/data transfer is timed separately. The render budget below
      // still starts at this run's actual data arrival and remains exactly1s.
      await expect(timeline.locator(".event-row").nth(1)).toBeVisible({
        timeout: 60000,
      });
      await timeline.locator(".event-row").nth(1).click();
      await expect(timeline.locator(".event-row").nth(1)).toHaveClass(
        /focused/,
      );
      const timing = await page.evaluate(() => {
        const arrival = (window as unknown as { sentinelDataArrival: number })
          .sentinelDataArrival;
        if (!arrival) throw new Error("timeline data arrival was not observed");
        return {
          afterData: (performance.now() - arrival) / 1000,
          navigationToData: arrival / 1000,
        };
      });
      samples.push(timing.afterData);
      navigationToData.push(timing.navigationToData);
      // Only the selected500-event page is loaded; the visible rows remain virtualized.
      expect(await timeline.locator(".event-row").count()).toBeLessThan(50);
      await (await settled).finished();
    }
    const sorted = [...samples].sort((a, b) => a - b);
    const p95 = sorted[Math.ceil(0.95 * sorted.length) - 1];
    await writeFile(
      target === 3186
        ? "../.local-controller/ui-validation/timeline-performance.json"
        : "../.local-controller/ui-validation/timeline-performance-50000.json",
      JSON.stringify(
        {
          schema_version: 1,
          scope:
            "Chromium, same host, production Next server and loopback SQLite fixture; not PostgreSQL concurrency",
          timeline_interactive_after_data: {
            run_id: run.run_id,
            journal_root: run.journal_root,
            boundaries: run.records,
            n: samples.length,
            samples_seconds: samples,
            p50_seconds: sorted[Math.ceil(0.5 * sorted.length) - 1],
            p95_seconds: p95,
            measurement:
              "latest parsed timeline/incidents response to confirmed second-row focus; includes test-driver interaction cost",
          },
          page_errors: errors,
          navigation_to_data_seconds: navigationToData,
          cold_first_navigation_to_data_seconds: navigationToData[0],
        },
        null,
        2,
      ) + "\n",
    );
    expect(errors).toEqual([]);
    expect(p95).toBeLessThanOrEqual(1);
  });
}
