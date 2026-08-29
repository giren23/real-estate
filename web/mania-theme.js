// This file is intentionally separate so the reference-inspired theme is easy to revert.
if (globalThis.Chart) {
  Chart.defaults.color = "#6f6976";
  Chart.defaults.borderColor = "rgba(75,52,120,.11)";
  Chart.defaults.plugins.legend.labels.color = "#4c4652";
  Chart.defaults.plugins.tooltip.backgroundColor = "#352653";
  Chart.defaults.plugins.tooltip.titleColor = "#fff";
  Chart.defaults.plugins.tooltip.bodyColor = "#f4effa";
  Chart.defaults.plugins.tooltip.borderColor = "#715b97";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
}
