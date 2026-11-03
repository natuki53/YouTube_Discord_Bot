// CSP に対応する外部スクリプト。初回描画より前にテーマを選ぶ。
try {
  const preference = localStorage.getItem("music-theme") || "system";
  const theme =
    preference === "light" || preference === "dark"
      ? preference
      : matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
} catch {
  document.documentElement.dataset.theme = "dark";
}
