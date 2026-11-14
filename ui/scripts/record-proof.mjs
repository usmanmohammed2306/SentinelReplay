// Continuous capture of the real local deployment. No results are fabricated.
import { chromium, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const [origin, envFile, runId, outputArg] = process.argv.slice(2);
if (
  !origin ||
  !envFile ||
  !runId ||
  !outputArg ||
  !/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)
)
  throw new Error(
    "Expected loopback origin, private env file, run ID and output directory",
  );
const output = resolve(outputArg);
await mkdir(output, { recursive: true, mode: 0o700 });
const config = Object.fromEntries(
  (await readFile(envFile, "utf8"))
    .trim()
    .split("\n")
    .map((line) => {
      const split = line.indexOf("=");
      return [line.slice(0, split), line.slice(split + 1)];
    }),
);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: output, size: { width: 1440, height: 1000 } },
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const started = performance.now();
const moments = [];
async function caption(text) {
  await page.evaluate((text) => {
    let item = document.getElementById("proof-caption");
    if (!item) {
      item = document.createElement("div");
      item.id = "proof-caption";
      item.style.cssText =
        "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:99999;padding:14px 24px;background:#0c1718f5;border:1px solid #75e6ba77;color:#e9fff5;border-radius:12px;font:16px system-ui;box-shadow:0 8px 30px #0009;pointer-events:none;max-width:90vw;text-align:center";
      document.body.append(item);
    }
    item.textContent = text;
  }, text);
  moments.push({
    seconds: (performance.now() - started) / 1000,
    caption: text,
  });
}
async function until(seconds) {
  const remaining = seconds * 1000 - (performance.now() - started);
  if (remaining > 0) await page.waitForTimeout(remaining);
}
try {
  await page.goto(origin);
  await caption(
    "Sentinel Replay · An investigation backed by recorded evidence",
  );
  await page
    .getByLabel("Investigator access token")
    .fill(config.SENTINEL_API_TOKEN);
  await page.getByRole("button", { name: "Open investigation" }).click();
  await expect(
    page.getByRole("heading", { name: "Follow the evidence." }),
  ).toBeVisible();
  await page.locator(`[data-run-id="${runId}"]`).click();
  await page.getByRole("button", { name: "Timeline", exact: true }).click();
  await expect(
    page.getByText("Protected materialization", { exact: true }),
  ).toBeVisible();
  await caption(
    "3,186 recorded boundaries. Six phases. Follow the protected value.",
  );
  await page.locator(".phase-navigator summary").click();
  await page.screenshot({
    path: join(output, "timeline-desktop.png"),
    fullPage: true,
  });
  await until(13);
  await page.getByRole("button", { name: "Provenance", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Root step" }).fill("3181");
  await expect(page.getByLabel("Declared dependency graph")).toBeVisible();
  await caption(
    "Declared provenance separates data dependencies from simple sequence.",
  );
  await page.screenshot({
    path: join(output, "provenance-desktop.png"),
    fullPage: true,
  });
  await until(24);
  await page.getByRole("button", { name: "Replay lab", exact: true }).click();
  await page
    .getByRole("button", { name: "Restore and match boundaries" })
    .click();
  await expect(
    page.getByRole("heading", { name: "VERIFIED_REPLAY", exact: true }),
  ).toBeVisible({ timeout: 25000 });
  await caption(
    "Restored workspace, Git and SQLite. Covered finite effects re-executed.",
  );
  await page.screenshot({
    path: join(output, "replay-desktop.png"),
    fullPage: true,
  });
  await until(38);
  await page
    .getByRole("button", { name: "Policies & futures", exact: true })
    .click();
  await expect(page.getByLabel("Verified policy source")).toBeVisible();
  await caption(
    "Three executed policies: preserve the public task while blocking the simulated export.",
  );
  await page.screenshot({
    path: join(output, "policies-desktop.png"),
    fullPage: true,
  });
  await until(52);
  await page.getByRole("button", { name: "World diff", exact: true }).click();
  await expect(
    page.getByText("∆ egress.txt", { exact: true }).first(),
  ).toBeVisible();
  await caption(
    "Compare actual covered file changes. These futures are labeled simulations.",
  );
  await until(62);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await page.getByRole("button", { name: "Recheck stored evidence" }).click();
  await expect(page.getByRole("status")).toContainText(
    "cryptographic_signature_valid",
  );
  await caption(
    "Signed portable capsule. Encrypted storage. Explicit coverage and freshness limits.",
  );
  await page.screenshot({
    path: join(output, "evidence-desktop.png"),
    fullPage: true,
  });
  await until(75);
  if (errors.length) throw new Error("Browser errors: " + errors.join("; "));
  await context.close();
  await page.video().saveAs(join(output, "sentinel-replay-proof.webm"));
  await writeFile(
    join(output, "capture.json"),
    JSON.stringify(
      {
        continuous_capture: true,
        requested_seconds: 75,
        run_id: runId,
        moments,
        errors,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
