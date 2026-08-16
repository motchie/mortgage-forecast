import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatRate, formatTenThousandYen, formatYen } from "../formatters";
import type { SensitivityCase } from "../types";
import { ScrollableTable } from "./ScrollableTable";

export interface Series { id: string; label: string; points: Array<{ date: string; value: number }> }
const styles = [
  { stroke: "#1b5a47", dash: undefined },
  { stroke: "#356f92", dash: "8 4" },
  { stroke: "#8a611c", dash: "3 3" },
  { stroke: "#744d6a", dash: "12 4 2 4" },
];

function mergeSeries(series: Series[]) {
  const rows = new Map<string, Record<string, string | number>>();
  series.forEach((item) => item.points.forEach((point) => {
    const date = point.date.slice(0, 7);
    const row = rows.get(date) ?? { date };
    row[item.id] = point.value;
    rows.set(date, row);
  }));
  return [...rows.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function yearlyRows(series: Series[]) {
  return series.flatMap((item) => {
    const byYear = new Map<string, { date: string; value: number }>();
    item.points.forEach((point) => byYear.set(point.date.slice(0, 4), point));
    return [...byYear].map(([year, point]) => ({ year, scenario: item.label, value: point.value }));
  });
}

export function ForecastLineChart({ title, description, series, valueLabel }: { title: string; description: string; series: Series[]; valueLabel: string }) {
  const [showTable, setShowTable] = useState(false);
  const data = useMemo(() => mergeSeries(series), [series]);
  const tableRows = useMemo(() => yearlyRows(series), [series]);
  return <article className="chart-card">
    <div className="chart-heading"><div><h3>{title}</h3><p>{description}</p></div><button className="text-button" type="button" onClick={() => setShowTable((value) => !value)} aria-expanded={showTable}>{showTable ? "データ表を閉じる" : "データ表を表示"}</button></div>
    <ul className="chart-legend" aria-label="シナリオ凡例">{series.map((item, index) => <li key={item.id}><span className={`line-key line-key-${index + 1}`} aria-hidden="true" />{item.label}</li>)}</ul>
    <p className="chart-axis-unit">縦軸単位：万円</p>
    <div className="chart-frame" role="img" aria-label={`${title}。縦軸の単位は万円です。詳細はデータ表で確認できます。`}><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 10, right: 18, bottom: 8, left: 10 }}><CartesianGrid stroke="#dce2dd" vertical={false} /><XAxis dataKey="date" minTickGap={44} tickFormatter={(value) => String(value).slice(0, 4)} /><YAxis width={86} tickFormatter={(value) => formatTenThousandYen(Number(value))} /><Tooltip formatter={(value) => formatYen(Number(value))} labelFormatter={(value) => String(value)} />{series.map((item, index) => <Line key={item.id} type="stepAfter" dataKey={item.id} name={item.label} stroke={styles[index]?.stroke} strokeDasharray={styles[index]?.dash} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls />)}</LineChart></ResponsiveContainer></div>
    {showTable && <ScrollableTable label={`${title}の年次データ`}><table><caption>{title}の年次データ</caption><thead><tr><th scope="col">年</th><th scope="col">シナリオ</th><th scope="col">{valueLabel}</th></tr></thead><tbody>{tableRows.map((row) => <tr key={`${row.year}-${row.scenario}`}><th scope="row">{row.year}年</th><td>{row.scenario}</td><td>{formatYen(row.value)}</td></tr>)}</tbody></table></ScrollableTable>}
  </article>;
}

export function SensitivityChart({ cases }: { cases: SensitivityCase[] }) {
  const data = cases.map((item) => ({ rate: formatRate(item.annual_rate), extra: item.extra_final_payment }));
  return <div><p className="chart-axis-unit">縦軸単位：万円</p><div className="chart-frame sensitivity-chart" role="img" aria-label="一定金利ごとの追加最終返済額。縦軸の単位は万円です。詳細は隣接する表で確認できます。"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 10, right: 18, bottom: 8, left: 10 }}><CartesianGrid stroke="#dce2dd" vertical={false} /><XAxis dataKey="rate" /><YAxis width={86} tickFormatter={(value) => formatTenThousandYen(Number(value))} /><Tooltip formatter={(value) => formatYen(Number(value))} /><Line type="monotone" dataKey="extra" name="追加最終返済額" stroke="#744d6a" strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div></div>;
}
