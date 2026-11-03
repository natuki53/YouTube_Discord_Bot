import { test, expect, type Page } from "@playwright/test";
const state = {
  guild: { id: "100", name: "Music Lounge" },
  current: {
    title: "夜の散歩に、いつものプレイリスト",
    url: "https://www.youtube.com/watch?v=abcdefghijk",
    requester: "natuki",
    video_id: null,
    auto_selected: false,
  },
  queue: [
    {
      title: "雨上がりの街を歩く",
      url: "https://www.youtube.com/watch?v=12345678901",
      requester: "haru",
      video_id: null,
      auto_selected: false,
    },
    {
      title: "コーヒーと、日曜日。",
      url: "https://www.youtube.com/watch?v=23456789012",
      requester: "natuki",
      video_id: null,
      auto_selected: false,
    },
  ],
  loop: false,
  autoplay: false,
  volume: 25,
  voice_channel: "ラウンジ",
  paused: false,
  connected: true,
  can_control: true,
  control_reason: "",
  can_manage: true,
  notification_channel_id: "10",
  channels: [
    { id: "10", name: "music" },
    { id: "11", name: "bot" },
  ],
  jobs: [],
};
async function mock(page: Page, authed = true) {
  let jobs: unknown[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/me")
      return route.fulfill({
        status: authed ? 200 : 401,
        json: authed
          ? {
              user: { id: "1", username: "natuki", global_name: "natuki" },
              csrf: "test-csrf",
            }
          : { error: "ログインしてください。" },
      });
    if (url.pathname === "/api/guilds")
      return route.fulfill({
        json: {
          guilds: [
            { id: "100", name: "Music Lounge", icon: null },
            { id: "200", name: "Friends", icon: null },
          ],
        },
      });
    if (url.pathname.endsWith("/volume"))
      return route.fulfill({
        json: { volume: route.request().postDataJSON().volume },
      });
    if (url.pathname.endsWith("/state"))
      return route.fulfill({
        json: {
          ...state,
          jobs,
          guild: url.pathname.includes("/200/")
            ? { id: "200", name: "Friends" }
            : state.guild,
        },
      });
    if (
      route.request().method() === "POST" &&
      route.request().postDataJSON().action === "playlist_preview"
    ) {
      jobs = [
        {
          id: "preview-job",
          action: "playlist_preview",
          status: "done",
          message: "曲数を選んでください。",
          preview: {
            id: "preview-token",
            query: "https://www.youtube.com/playlist?list=PL123",
            title: "みんなのプレイリスト",
            maximum: 50,
            available: 50,
            skipped: 1,
            truncated: true,
            tracks: ["First song", "Second song"],
          },
        },
      ];
      return route.fulfill({
        status: 202,
        json: {
          id: "preview-job",
          action: "playlist_preview",
          status: "running",
          message: "再生リストを確認しています…",
        },
      });
    }
    return route.fulfill({
      status: 202,
      json: {
        id: "operation",
        action: "play",
        status: "running",
        message: "曲を確認しています…",
      },
    });
  });
}
test("ログイン前の画面とDiscord認証リンク", async ({ page }) => {
  await mock(page, false);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /いつものVCに/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Discordでログイン" }),
  ).toHaveAttribute("href", "/auth/login");
  await expect(page.locator("body")).not.toHaveJSProperty("scrollWidth", 0);
  await page.screenshot({
    path: `test-results/login-${test.info().project.name}.png`,
    fullPage: true,
  });
});
test("再生画面・キューとレスポンシブ表示", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: state.current.title }),
  ).toBeVisible();
  await expect(page.getByText("雨上がりの街を歩く")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `test-results/player-${test.info().project.name}.png`,
    fullPage: true,
  });
});
test("曲の追加はCSRF・一意の操作IDとサーバーIDを送信", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByLabel("曲名・YouTube URL").fill("好きな曲");
  const request = page.waitForRequest((r) => r.url().endsWith("/100/actions"));
  await page.getByRole("button", { name: "キューに追加" }).click();
  const r = await request;
  expect(r.headers()["x-csrf-token"]).toBe("test-csrf");
  expect(r.headers()["x-request-id"]).toBeTruthy();
  expect(r.postDataJSON()).toMatchObject({ action: "play", query: "好きな曲" });
  await expect(page.getByRole("status")).toContainText("曲を確認しています");
});
test("サーバーの切り替えとダウンロード画面", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: state.current.title }),
  ).toBeVisible();
  await page.getByLabel("Discordサーバー").selectOption("200");
  await expect(page.getByLabel("Discordサーバー")).toHaveValue("200");
  await page.getByRole("button", { name: "ダウンロード", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "動画・音声をDiscordへ" }),
  ).toBeVisible();
  await page.getByLabel("形式").selectOption("mp3");
  await expect(page.getByLabel("画質")).toHaveCount(0);
});
test("管理者は通知先を設定できる", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByRole("button", { name: "サーバー設定" }).click();
  await page.getByLabel("再生通知・ファイルの送信先").selectOption("11");
  const request = page.waitForRequest((r) => r.url().endsWith("/settings"));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  expect((await request).postDataJSON()).toEqual({ channel_id: "11" });
});
test("テーマ切り替え・保存・端末設定への追従", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByLabel("表示テーマ").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: `test-results/player-dark-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.getByLabel("表示テーマ").selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({
    path: `test-results/player-light-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByLabel("表示テーマ")).toHaveValue("light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("表示テーマ").selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
test("再生リストは曲数を選び確認してから取り込む", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const plays: unknown[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/actions") && r.postDataJSON()?.action === "play")
      plays.push(r.postDataJSON());
  });
  await page
    .getByLabel("曲名・YouTube URL")
    .fill("https://www.youtube.com/playlist?list=PL123");
  await page.getByRole("button", { name: "再生リストを確認" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(plays).toHaveLength(0);
  await expect(page.getByLabel("取り込む曲数")).toHaveValue("50");
  await page.getByLabel("取り込む曲数").fill("7");
  await page.screenshot({
    path: `test-results/playlist-${test.info().project.name}.png`,
    fullPage: true,
  });
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/actions") && r.postDataJSON().action === "play",
  );
  await page.getByRole("button", { name: "7曲を取り込む" }).click();
  expect((await request).postDataJSON()).toMatchObject({
    count: 7,
    preview_id: "preview-token",
  });
});

test("音量ドラッグ中の定期更新が値とフォーカスを上書きしない", async ({
  page,
}) => {
  await mock(page);
  await page.clock.install();
  await page.goto("/");
  const slider = page.getByRole("slider", { name: "音量" });
  await expect(slider).toBeEnabled();
  const element = await slider.elementHandle();
  const box = (await slider.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height / 2);
  const desired = await slider.inputValue();
  expect(Number(desired)).toBeGreaterThan(60);
  await page.clock.fastForward(3000);
  await page.clock.fastForward(3000);
  await expect(slider).toHaveValue(desired);
  expect(await element!.evaluate((el) => el.isConnected)).toBeTruthy();
  const saved = page.waitForRequest(
    (r) => r.url().endsWith("/volume") && r.method() === "PUT",
  );
  await page.mouse.up();
  expect((await saved).postDataJSON().volume).toBe(Number(desired));
});

test("通知の表示と消去で操作パネルが移動しない", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const panel = page.locator(".now-playing");
  await expect(panel).toBeVisible();
  const before = (await panel.boundingBox())!;
  await page.getByRole("button", { name: "一時停止", exact: true }).click();
  await expect(page.locator(".toast-stack [role=status]")).toBeVisible();
  expect((await panel.boundingBox())!.y).toBe(before.y);
  await page.getByRole("button", { name: "通知を閉じる" }).click();
  expect((await panel.boundingBox())!.y).toBe(before.y);
});

test("状態取得が一度失敗してもドラッグ中の操作パネルを消さない", async ({
  page,
}) => {
  await mock(page);
  await page.clock.install();
  await page.goto("/");
  const slider = page.getByRole("slider", { name: "音量" });
  await expect(slider).toBeEnabled();
  const element = await slider.elementHandle();
  await page.route("**/api/guilds/100/state", (route) =>
    route.fulfill({ status: 503, json: { error: "一時的な通信エラー" } }),
  );
  const box = (await slider.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height / 2);
  const desired = await slider.inputValue();
  await page.clock.fastForward(3000);
  await expect(page.getByRole("alert")).toBeVisible();
  expect(await element!.evaluate((el) => el.isConnected)).toBeTruthy();
  await expect(slider).toHaveValue(desired);
  await page.mouse.up();
});

test("音量保存より前に始まった古い更新結果を反映しない", async ({ page }) => {
  await mock(page);
  await page.clock.install();
  let reads = 0;
  let release: (() => void) | undefined;
  let currentVolume = 25;
  await page.route("**/api/guilds/100/state", async (route) => {
    const snapshot = { ...state, volume: currentVolume };
    if (++reads === 2)
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    await route.fulfill({ json: snapshot });
  });
  await page.route("**/api/guilds/100/volume", async (route) => {
    currentVolume = route.request().postDataJSON().volume;
    await route.fulfill({ json: { volume: currentVolume } });
  });
  await page.goto("/");
  const slider = page.getByRole("slider", { name: "音量" });
  await expect(slider).toBeEnabled();
  await page.clock.fastForward(3000);
  await expect.poll(() => reads).toBe(2);
  await slider.focus();
  await slider.press("End");
  await expect(slider).toHaveValue("100");
  await expect.poll(() => currentVolume).toBe(100);
  release!();
  await expect(slider).toHaveValue("100");
});
