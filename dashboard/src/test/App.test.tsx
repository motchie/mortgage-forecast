import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { ForecastDocument } from "../types";
import forecast from "./forecast-fixture";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  Line: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

function mockForecast(document: ForecastDocument = forecast) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => document }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("住宅ローン予測ダッシュボード", () => {
  it("sample現在値、ローン、4シナリオ、検証状態を表示する", async () => {
    mockForecast();
    render(<App />);

    expect(screen.getByText("データを読み込んでいます")).toBeInTheDocument();
    const currentHeading = await screen.findByRole("heading", { name: "ローンの現在地" });
    const currentPanel = currentHeading.closest("section");
    expect(currentPanel).not.toBeNull();
    expect(within(currentPanel!).getByText("14,000,000円")).toBeInTheDocument();
    expect(within(currentPanel!).getByText("65,000円")).toBeInTheDocument();
    expect(within(currentPanel!).getByText("6,000,000円")).toBeInTheDocument();
    expect(within(currentPanel!).getByText("30%")).toBeInTheDocument();
    expect(screen.getAllByText("返済済み元金")).toHaveLength(2);
    expect(screen.getAllByText("元金返済率")).toHaveLength(2);
    expect(screen.getAllByRole("heading", { name: "Example variable-rate loan" })).toHaveLength(2);
    expect(screen.getByText("PUBLIC DEMO · ARTIFICIAL SAMPLE DATA")).toBeInTheDocument();
    expect(screen.getByText(/人工サンプルデータによる公開デモ/)).toBeInTheDocument();
    expect(screen.getByText(/公開デモ用の人工データ/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Base" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Higher" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Stress" })).toBeInTheDocument();
    expect(screen.getByText("現在の金利が続く機械的ケース")).toBeInTheDocument();
    expect(screen.getAllByText("将来金利についての手動仮定")).toHaveLength(3);
    expect(screen.getByText("現在金利1.8%を継続")).toBeInTheDocument();
    expect(screen.getByText("現在金利 → 2027年1月1日の次回返済から2%（以後継続）")).toBeInTheDocument();
    expect(screen.getByText("現在金利 → 2027年1月1日の次回返済から3%（以後継続）")).toBeInTheDocument();
    expect(screen.getByText("現在金利 → 2027年1月1日の次回返済から5%（以後継続）")).toBeInTheDocument();
    expect(screen.getByText("Golden tests validated")).toBeInTheDocument();
    expect(screen.getByText("4か月検証済み")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "一定金利ごとの返済リスク" })).toBeInTheDocument();
    const sensitivityTable = screen.getByRole("table", { name: "一定金利ごとの返済リスク" });
    expect(within(sensitivityTable).getByRole("columnheader", { name: "備考" })).toHaveClass("remarks-cell");
    expect(within(sensitivityTable).getByRole("row", { name: /1.8%/ })).toHaveTextContent("現在金利");
    expect(within(sensitivityTable).getByRole("row", { name: /3%/ })).toHaveTextContent("主要比較金利");
    expect(within(sensitivityTable).getByRole("row", { name: /5%/ })).toHaveTextContent("主要比較金利・追加最終返済あり");
    expect(within(sensitivityTable).getByText("主要比較金利・追加最終返済あり")).toHaveClass("remarks-cell");
    expect(within(sensitivityTable).queryByRole("row", { name: /1.8%/ })).not.toHaveClass("highlight-row");
    expect(screen.getAllByText("未検証仮定あり").length).toBeGreaterThan(0);
    expect(screen.getByText(/モデル仕様やデータ品質に関する表示/)).toBeInTheDocument();
    expect(screen.getByText(/将来シナリオの正確さや金利予測を意味しません/)).toBeInTheDocument();
  });

  it("短期プライム連動シナリオはローンごとの貸出金利を表示する", async () => {
    const secondLoan = {
      ...forecast.loans[0],
      id: "second-loan",
      display_name: "Second variable-rate loan",
      rate_model: { ...forecast.loans[0].rate_model, spread: -0.0049 },
    };
    const document: ForecastDocument = {
      ...forecast,
      loans: [...forecast.loans, secondLoan],
      scenarios: forecast.scenarios.map((scenario) => {
        if (scenario.id !== "base" && scenario.id !== "stress") return scenario;
        const finalRate = scenario.id === "stress" ? 0.03475 : 0.03525;
        return {
          ...scenario,
          type: "short_prime_path",
          rates: [
            { effective_date: "2036-01-10", annual_rate: 0.03125 },
            { effective_date: "2037-01-10", annual_rate: 0.03225 },
            { effective_date: "2038-01-10", annual_rate: 0.03325 },
            { effective_date: "2039-01-10", annual_rate: 0.03425 },
            { effective_date: "2040-01-10", annual_rate: finalRate },
          ],
          terminal_rate: finalRate,
        };
      }),
    };
    mockForecast(document);
    render(<App />);

    expect(await screen.findByText("現在金利 → 2036年から毎年0.1ポイントずつ上昇（各年1月10日の次回返済から適用） → 2040年にexample-loan 3.025% / second-loan 3.035%（以後継続）")).toBeInTheDocument();
    expect(screen.getByText("現在金利 → 2036年から毎年0.1ポイントずつ上昇（各年1月10日の次回返済から適用） → 2040年にexample-loan 2.975% / second-loan 2.985%で頭打ち")).toBeInTheDocument();
  });

  it("予定返済で前進した現在値を実績と誤認させない", async () => {
    mockForecast({
      ...forecast,
      loans: forecast.loans.map((loan) => ({
        ...loan,
        current: {
          ...loan.current,
          balance: 13_956_000,
          balance_date: "2026-09-20",
          assumed_payment_count: 1,
          verification_status: "inferred",
        },
      })),
      combined: { ...forecast.combined, current_balance: 13_956_000 },
    });
    render(<App />);

    expect(await screen.findByText("Current / 推定現在値")).toBeInTheDocument();
    expect(screen.getByText(/実際の引き落とし確認ではありません/)).toBeInTheDocument();
    expect(screen.getByText("銀行確認基準日")).toBeInTheDocument();
    expect(screen.getByText("仮定した返済")).toBeInTheDocument();
  });

  it("表示対象とグラフの代替表をキーボード操作可能なUIで切り替える", async () => {
    mockForecast();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "金利仮定ごとの返済リスク" });

    const picker = screen.getByRole("combobox", { name: "表示対象" });
    const trendPicker = screen.getByRole("combobox", { name: "推移の表示対象" });
    await user.selectOptions(picker, "example-loan");
    expect(picker).toHaveValue("example-loan");
    expect(trendPicker).toHaveValue("example-loan");

    await user.selectOptions(trendPicker, "combined");
    expect(trendPicker).toHaveValue("combined");
    expect(picker).toHaveValue("combined");

    const toggles = screen.getAllByRole("button", { name: "データ表を表示" });
    await user.click(toggles[0]);
    const balanceTable = screen.getByRole("table", { name: "残高推移の年次データ" });
    expect(balanceTable).toBeInTheDocument();
    expect(within(balanceTable).getByRole("columnheader", { name: "その年に迎える年齢" })).toBeInTheDocument();
    expect(within(balanceTable).getAllByText("46歳").length).toBeGreaterThan(0);
    expect(toggles[0]).toHaveAttribute("aria-expanded", "true");
  });

  it("ペアローン合計の年次表に両方の契約者年齢を表示する", async () => {
    const secondLoan = {
      ...forecast.loans[0],
      id: "second-loan",
      display_name: "Second variable-rate loan",
      borrower_birth_year: 1975,
    };
    mockForecast({
      ...forecast,
      presentation: { show_trend_charts: false },
      loans: [...forecast.loans, secondLoan],
    });
    render(<App />);

    const balanceTable = await screen.findByRole("table", { name: "残高推移の年次データ" });
    expect(within(balanceTable).getAllByText("example-loan 46歳 / second-loan 51歳").length).toBeGreaterThan(0);
  });

  it("設定で推移グラフを非表示にし、データ表だけを表示する", async () => {
    mockForecast({ ...forecast, presentation: { show_trend_charts: false } });
    render(<App />);
    await screen.findByRole("heading", { name: "残高と月返済額の推移" });

    expect(screen.queryByRole("img", { name: /残高推移。/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /月返済額推移。/ })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "残高推移の年次データ" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "月返済額推移の年次データ" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "データ表を表示" })).not.toBeInTheDocument();
  });

  it("ペアローン合計では同じモデル上の注意を1件だけ表示する", async () => {
    const stress = forecast.combined.scenarios.find((scenario) => scenario.scenario_id === "stress")!;
    const warning = stress.warnings[0];
    const document: ForecastDocument = {
      ...forecast,
      combined: {
        ...forecast.combined,
        scenarios: forecast.combined.scenarios.map((scenario) => scenario.scenario_id === "stress" ? {
          ...scenario,
          warnings: [warning, { ...warning, scope: { ...warning.scope, loan_id: "second-loan" } }],
        } : scenario),
      },
    };
    mockForecast(document);
    render(<App />);

    const heading = await screen.findByRole("heading", { name: "Stress" });
    const card = heading.closest("article");
    expect(card).not.toBeNull();
    expect(within(card!).getByText("モデル上の注意 1件")).toBeInTheDocument();
    expect(within(card!).getAllByText("最終回の利息期間・端数処理は未検証")).toHaveLength(1);
  });

  it("主要画面に自動検出可能なアクセシビリティ違反がない", async () => {
    mockForecast();
    const { container } = render(<App />);
    await screen.findByRole("heading", { name: "モデル上の注意と前提" });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("JSONの読み込み失敗を説明する", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "住宅ローンデータを読み込めませんでした。" })).toBeInTheDocument());
    expect(screen.getByText("forecast.jsonを生成済みか確認してください。")).toBeInTheDocument();
  });
});
