import type { ReactElement, ReactNode } from "react";
import { ResponsiveContainer } from "recharts";
import { CHART } from "../lib/colors";
import { usePrefs } from "../lib/prefs";
import { Empty } from "./ui";

export function useChartTheme() {
  const { isDark } = usePrefs();
  const mode = isDark ? "dark" : "light";
  return {
    grid: CHART.grid[mode],
    axis: CHART.axis[mode],
    tick: { fill: CHART.axis[mode], fontSize: 11 },
    tooltip: {
      contentStyle: {
        background: isDark ? "#0f172a" : "#ffffff",
        border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`,
        borderRadius: 8,
        fontSize: 12,
        color: isDark ? "#e2e8f0" : "#0f172a",
      },
      cursor: { fill: isDark ? "rgba(148,163,184,0.08)" : "rgba(100,116,139,0.08)" },
    },
  };
}

export function ChartBox({ height = 240, empty, children }: { height?: number; empty?: boolean; children: ReactNode }) {
  const { t } = usePrefs();
  if (empty) return <Empty message={t("ov.noData")} />;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children as ReactElement}
      </ResponsiveContainer>
    </div>
  );
}
