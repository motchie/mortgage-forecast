import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
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

function mockForecast() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => forecast }));
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
    expect(screen.getAllByRole("heading", { name: "Example variable-rate loan" })).toHaveLength(2);
    expect(screen.getByText("LOCAL ONLY · SAMPLE DATA")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Base" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Higher" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Stress" })).toBeInTheDocument();
    expect(screen.getByText("現在の金利が続く機械的ケース")).toBeInTheDocument();
    expect(screen.getAllByText("将来金利についての手動仮定")).toHaveLength(3);
    expect(screen.getByText("Golden tests validated")).toBeInTheDocument();
    expect(screen.getByText("4か月検証済み")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "一定金利ごとの返済リスク" })).toBeInTheDocument();
    expect(screen.getAllByText("未検証仮定あり").length).toBeGreaterThan(0);
    expect(screen.getByText(/モデル仕様やデータ品質に関する表示/)).toBeInTheDocument();
    expect(screen.getByText(/将来シナリオの正確さや金利予測を意味しません/)).toBeInTheDocument();
  });

  it("表示対象とグラフの代替表をキーボード操作可能なUIで切り替える", async () => {
    mockForecast();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "金利仮定ごとの返済リスク" });

    const picker = screen.getByRole("combobox", { name: "表示対象" });
    await user.selectOptions(picker, "example-loan");
    expect(picker).toHaveValue("example-loan");

    const toggles = screen.getAllByRole("button", { name: "データ表を表示" });
    await user.click(toggles[0]);
    expect(screen.getByRole("table", { name: "残高推移の年次データ" })).toBeInTheDocument();
    expect(toggles[0]).toHaveAttribute("aria-expanded", "true");
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
