"use client";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Comparison } from "@/lib/types";

export default function PolicyChart({
  comparison,
}: {
  comparison: Comparison;
}) {
  return (
    <div
      className="chart"
      role="img"
      aria-label="Policy tradeoff: task disruption versus rule complexity"
    >
      <ResponsiveContainer width="100%" height={230}>
        <ScatterChart margin={{ top: 20, right: 35, bottom: 20, left: 0 }}>
          <CartesianGrid stroke="#263239" strokeDasharray="4 4" />
          <XAxis
            type="number"
            dataKey="task_disruption"
            name="Lost full tasks"
            label={{
              value: "Lost full tasks",
              position: "bottom",
              fill: "#8d9b9e",
            }}
            allowDecimals={false}
            stroke="#829093"
          />
          <YAxis
            type="number"
            dataKey="rule_complexity"
            name="Rule complexity"
            allowDecimals={false}
            stroke="#829093"
          />
          <Tooltip
            contentStyle={{
              background: "#172024",
              border: "1px solid #344249",
            }}
          />
          <Scatter
            name="Executed candidates"
            data={comparison.scores}
            fill="#d2a45f"
          />
          <Scatter
            name="Preventing frontier"
            data={comparison.scores.filter((row) =>
              comparison.frontier.includes(row.arm),
            )}
            fill="#7dc4ac"
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
