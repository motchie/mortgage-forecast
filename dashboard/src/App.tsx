import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { AgeReference, Series } from "./components/Charts";
import { ScrollableTable } from "./components/ScrollableTable";
import { loadForecast } from "./data";
import { formatDate, formatDateTime, formatPercentage, formatRate, formatYen } from "./formatters";
import type { CombinedScenario, ForecastDocument, ModelWarning, Scenario, ScenarioResult, SensitivityCase } from "./types";
import "./styles.css";

const ForecastLineChart = lazy(() => import("./components/Charts").then((module) => ({ default: module.ForecastLineChart })));
const SensitivityChart = lazy(() => import("./components/Charts").then((module) => ({ default: module.SensitivityChart })));

const DISPLAY_SCENARIOS = ["current", "base", "higher", "stress"];
const warningLabels: Record<string, string> = {
  UNVERIFIED_UNPAID_INTEREST_REVIEW: "未払利息がある見直しに未検証の計算仮定を使用",
  UNVERIFIED_FINAL_PAYMENT: "最終回の利息期間・端数処理は未検証",
  NON_CONTRACTUAL_REVIEW_SCHEDULE: "見直し日程は公式商品ルールに基づくが契約上は未確認",
  INFERRED_RATE_SPREAD: "短期プライムレートのspreadは実績から推定",
  INFERRED_INTEREST_BALANCE_UNIT: "付利残高100円単位は銀行実績から推定",
  STALE_SCENARIO: "シナリオの更新日が基準日より古い",
};

interface ScenarioView {
  next: ScenarioResult["next_payment_review"];
  maximumPayment: number;
  capCount: number;
  capEvents: ScenarioResult["payment_cap_events"];
  unpaid: ScenarioResult["unpaid_interest"];
  finalPayment: number;
  extraFinalPayment: number;
  totalInterest: number;
  warnings: ModelWarning[];
}

function warningText(warning: ModelWarning) {
  return warningLabels[warning.code] ?? warning.message;
}

function uniqueWarnings(warnings: ModelWarning[]) {
  return [...new Map(warnings.map((warning) => [warning.code, warning])).values()];
}

function loanView(result: ScenarioResult): ScenarioView {
  return { next: result.next_payment_review, maximumPayment: result.maximum_monthly_payment, capCount: result.payment_cap_trigger_count, capEvents: result.payment_cap_events, unpaid: result.unpaid_interest, finalPayment: result.final_payment, extraFinalPayment: result.extra_final_payment, totalInterest: result.total_interest_paid, warnings: result.warnings };
}

function combinedView(result: CombinedScenario): ScenarioView {
  return { next: result.next_payment_review, maximumPayment: result.maximum_combined_monthly_payment, capCount: result.payment_cap_trigger_count, capEvents: result.payment_cap_events, unpaid: result.unpaid_interest, finalPayment: result.combined_final_payment, extraFinalPayment: result.combined_extra_final_payment, totalInterest: result.combined_total_interest_paid, warnings: result.warnings };
}

function rateAssumption(scenario: Scenario, data: ForecastDocument, scope: string): string {
  if (scenario.type === "constant_loan_rate") {
    if (scenario.rate_source === "loan_current" || scenario.annual_rate == null) {
      const loans = scope === "combined" ? data.loans : data.loans.filter((loan) => loan.id === scope);
      const rates = loans.map((loan) => `${scope === "combined" && loans.length > 1 ? `${loan.id} ` : ""}${formatRate(loan.current.annual_rate)}`);
      return `現在金利${rates.length === 1 ? rates[0] : `（${rates.join(" / ")}）`}を継続`;
    }
    return `${formatRate(scenario.annual_rate)}を継続`;
  }

  const points = scenario.rates ?? [];
  const loans = scope === "combined" ? data.loans : data.loans.filter((loan) => loan.id === scope);
  const formatScenarioRate = (annualRate: number) => {
    if (scenario.type !== "short_prime_path") return formatRate(annualRate);
    const rates = loans.map((loan) => `${scope === "combined" && loans.length > 1 ? `${loan.id} ` : ""}${formatRate(annualRate + loan.rate_model.spread)}`);
    return rates.join(" / ");
  };
  if (points.length >= 4) {
    const years = points.map((point) => Number(point.effective_date.slice(0, 4)));
    const monthDays = points.map((point) => point.effective_date.slice(5));
    const increments = points.slice(1).map((point, index) => point.annual_rate - points[index].annual_rate);
    const step = increments[0];
    const tolerance = 1e-9;
    const annual = years.every((year, index) => index === 0 || year === years[index - 1] + 1)
      && monthDays.every((monthDay) => monthDay === monthDays[0]);
    const regularBeforeLast = increments.slice(0, -1).every((increment) => Math.abs(increment - step) < tolerance);
    const lastIncrement = increments.at(-1) ?? step;
    const capped = regularBeforeLast && lastIncrement > 0 && lastIncrement < step - tolerance;
    const regular = increments.every((increment) => Math.abs(increment - step) < tolerance);
    if (annual && step > 0 && (regular || capped)) {
      const [, month, day] = points[0].effective_date.split("-").map(Number);
      const finalRate = formatScenarioRate(scenario.terminal_rate ?? points.at(-1)!.annual_rate);
      const ending = capped ? `${finalRate}で頭打ち` : `${finalRate}（以後継続）`;
      return `現在金利 → ${years[0]}年から毎年${formatRate(step).replace("%", "ポイント")}ずつ上昇（各年${month}月${day}日の次回返済から適用） → ${years.at(-1)}年に${ending}`;
    }
  }
  const assumptions = ["現在金利", ...points.map((point) => `${formatDate(point.effective_date)}の次回返済から${formatScenarioRate(point.annual_rate)}`)];
  const lastRate = points.at(-1)?.annual_rate;
  if (scenario.terminal_rate != null && scenario.terminal_rate !== lastRate) {
    assumptions.push(`以後${formatScenarioRate(scenario.terminal_rate)}`);
  } else if (points.length > 0) {
    assumptions[assumptions.length - 1] += "（以後継続）";
  }
  return assumptions.join(" → ");
}

function ScopePicker({ value, data, onChange, label = "表示対象" }: { value: string; data: ForecastDocument; onChange: (value: string) => void; label?: string }) {
  return <label className="scope-picker"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="combined">ペアローン合計</option>{data.loans.map((loan) => <option key={loan.id} value={loan.id}>{loan.display_name}</option>)}</select></label>;
}

function ScenarioCard({ scenario, view, rate }: { scenario: Scenario; view: ScenarioView; rate: string }) {
  const warnings = uniqueWarnings(view.warnings);
  const isCurrent = scenario.id === "current";
  const hasUnverifiedWarning = warnings.some((warning) => warning.verification_status === "unverified");
  return <article className={`scenario-card scenario-${scenario.id}`}>
    <div className="scenario-title"><div><p className="scenario-kind">{isCurrent ? "現在の金利が続く機械的ケース" : "将来金利についての手動仮定"}</p><h3>{isCurrent ? "Current" : scenario.label}</h3></div><span className="status-chip">{scenario.verification_status}</span></div>
    <p className="scenario-description">{scenario.description}</p>
    {hasUnverifiedWarning && <p className="inline-alert"><strong>未検証の計算仮定を含みます。</strong> 金額と併せて注意事項を確認してください。</p>}
    <dl className="data-list">
      <div className="rate-assumption-row"><dt>金利前提</dt><dd>{rate}</dd></div>
      <div><dt>次回見直し予想額</dt><dd>{view.next ? formatYen(view.next.expected_payment) : "—"}</dd></div>
      <div><dt>最大月返済額</dt><dd>{formatYen(view.maximumPayment)}</dd></div>
      <div><dt>125%上限発動</dt><dd>{view.capCount}回</dd></div>
      <div><dt>未払利息</dt><dd>{view.unpaid.ever_occurred ? "発生あり" : "なし"}</dd></div>
      <div><dt>初回発生日</dt><dd>{view.unpaid.first_date ? formatDate(view.unpaid.first_date) : "—"}</dd></div>
      <div><dt>最大未払利息</dt><dd>{formatYen(view.unpaid.maximum_amount)}</dd></div>
      <div className={hasUnverifiedWarning ? "result-warning-row" : ""}><dt>最終返済額{hasUnverifiedWarning && <small>未検証の計算仮定を含む</small>}</dt><dd>{formatYen(view.finalPayment)}</dd></div>
      <div className={`emphasis-row ${hasUnverifiedWarning ? "result-warning-row" : ""}`}><dt>追加最終返済額{hasUnverifiedWarning && <small>未検証の計算仮定を含む</small>}</dt><dd>{formatYen(view.extraFinalPayment)}</dd></div>
      <div><dt>総支払利息</dt><dd>{formatYen(view.totalInterest)}</dd></div>
    </dl>
    {warnings.length > 0 && <details className="card-warnings"><summary>モデル上の注意 {warnings.length}件</summary><ul>{warnings.map((warning) => <li key={warning.code}><span className={`severity severity-${warning.severity}`}>{warning.severity}</span>{warningText(warning)}</li>)}</ul></details>}
  </article>;
}

function Dashboard({ data }: { data: ForecastDocument }) {
  const isSample = data.data_source.type === "sample";
  const [scope, setScope] = useState("combined");
  const scenarios = data.scenarios.filter((scenario) => DISPLAY_SCENARIOS.includes(scenario.id));
  const maturity = data.loans.map((loan) => loan.maturity_date).sort().at(-1);
  const nextReview = data.loans.flatMap((loan) => loan.payment_review.schedule).sort()[0];

  const views = useMemo(() => new Map(scenarios.map((scenario) => {
    if (scope === "combined") {
      const result = data.combined.scenarios.find((item) => item.scenario_id === scenario.id);
      return [scenario.id, result ? combinedView(result) : null];
    }
    const result = scenario.results.find((item) => item.loan_id === scope);
    return [scenario.id, result ? loanView(result) : null];
  })), [data, scenarios, scope]);

  const balanceSeries: Series[] = scenarios.map((scenario) => {
    if (scope === "combined") {
      const result = data.combined.scenarios.find((item) => item.scenario_id === scenario.id)!;
      return { id: scenario.id, label: scenario.id === "current" ? "Current" : scenario.label, points: result.monthly_combined_balance_series.map((point) => ({ date: point.month, value: point.balance })) };
    }
    const result = scenario.results.find((item) => item.loan_id === scope)!;
    return { id: scenario.id, label: scenario.id === "current" ? "Current" : scenario.label, points: result.chart_data.balance_series.map((point) => ({ date: point.date, value: point.balance })) };
  });
  const paymentSeries: Series[] = scenarios.map((scenario) => {
    if (scope === "combined") {
      const result = data.combined.scenarios.find((item) => item.scenario_id === scenario.id)!;
      return { id: scenario.id, label: scenario.id === "current" ? "Current" : scenario.label, points: result.monthly_combined_payment_series.map((point) => ({ date: point.month, value: point.payment })) };
    }
    const result = scenario.results.find((item) => item.loan_id === scope)!;
    return { id: scenario.id, label: scenario.id === "current" ? "Current" : scenario.label, points: result.chart_data.payment_series.filter((point) => point.payment_type === "scheduled").map((point) => ({ date: point.date, value: point.monthly_payment })) };
  });
  const sensitivity: SensitivityCase[] = scope === "combined" ? data.combined.sensitivity : data.sensitivity.find((item) => item.loan_id === scope)?.cases ?? [];
  const ageReferences: AgeReference[] = data.loans
    .filter((loan) => (scope === "combined" || loan.id === scope) && loan.borrower_birth_year != null)
    .map((loan) => ({ label: loan.id, birthYear: loan.borrower_birth_year! }));
  const capEvents = [...views.entries()].flatMap(([scenarioId, view]) => view?.capEvents.filter((event) => event.cap_triggered).map((event) => ({ scenarioId, ...event })) ?? []);
  const groupedWarnings = [...new Map(data.warnings.map((warning) => [warning.code, warning])).values()];
  const totalOriginalPrincipal = data.loans.reduce((total, loan) => total + loan.original_principal, 0);
  const combinedRepaidPrincipal = Math.max(totalOriginalPrincipal - data.combined.current_balance, 0);
  const combinedRepaidRatio = totalOriginalPrincipal > 0 ? combinedRepaidPrincipal / totalOriginalPrincipal : 0;
  const assumedPaymentCount = data.loans.reduce((total, loan) => total + loan.current.assumed_payment_count, 0);
  const hasAssumedPayments = assumedPaymentCount > 0;
  const currentRates = new Set(data.loans
    .filter((loan) => scope === "combined" || loan.id === scope)
    .map((loan) => loan.current.annual_rate));

  return <>
    <header className="site-header"><div><p className="eyebrow">{isSample ? "PUBLIC DEMO · ARTIFICIAL SAMPLE DATA" : "PRIVATE · EXTERNAL DATA"}</p><h1>住宅ローン予測ダッシュボード</h1>{isSample && <p className="demo-notice" role="note">この画面は人工サンプルデータによる公開デモです。実在する契約・金融機関とは関係ありません。</p>}</div><p>最終生成: <time dateTime={data.generated_at}>{formatDateTime(data.generated_at)}</time></p></header>
    <main>
      <section className="current-panel" aria-labelledby="current-heading"><div className="section-heading"><p className="section-kicker">{hasAssumedPayments ? "Current / 推定現在値" : "Actual / 現在・実績"}</p><h2 id="current-heading">ローンの現在地</h2><p>{hasAssumedPayments ? `銀行確認済みの基準残高から、予定返済を合計${assumedPaymentCount}回実行したと仮定して更新した推定値です。実際の引き落とし確認ではありません。` : data.data_source.type === "sample" ? "架空のサンプル返済予定表を使った現在値です。" : "外部データディレクトリの銀行確認済み現在値です。"} 将来シナリオとは分けて表示しています。</p></div><div className="metric-grid"><article className="metric metric-primary"><span>現在残高</span><strong>{formatYen(data.combined.current_balance)}</strong></article><article className="metric"><span>月返済額</span><strong>{formatYen(data.combined.current_monthly_payment)}</strong></article><article className="metric"><span>返済済み元金</span><strong>{formatYen(combinedRepaidPrincipal)}</strong></article><article className="metric"><span>元金返済率</span><strong>{formatPercentage(combinedRepaidRatio)}</strong></article><article className="metric"><span>ローン本数</span><strong>{data.loans.length}本</strong></article><article className="metric"><span>最終返済日</span><strong>{maturity ? formatDate(maturity) : "—"}</strong></article><article className="metric"><span>次回返済額見直し</span><strong>{nextReview ? formatDate(nextReview) : "—"}</strong></article></div></section>

      <section className="section-block actual-block" aria-labelledby="loans-heading"><div className="section-heading"><p className="section-kicker">Current / Loan details</p><h2 id="loans-heading">ローンごとの現在値</h2></div><div className="loan-grid">{data.loans.map((loan) => { const repaidPrincipal = Math.max(loan.original_principal - loan.current.balance, 0); const repaidRatio = loan.original_principal > 0 ? repaidPrincipal / loan.original_principal : 0; return <article className="loan-card" key={loan.id}><div className="loan-card-title"><div><p>{loan.id}</p><h3>{loan.display_name}</h3></div><span className="status-chip">{loan.current.verification_status}</span></div><dl className="data-list"><div><dt>現在残高</dt><dd>{formatYen(loan.current.balance)}</dd></div><div><dt>残高基準日</dt><dd>{formatDate(loan.current.balance_date)}</dd></div>{loan.current.assumed_payment_count > 0 && <><div><dt>銀行確認基準日</dt><dd>{formatDate(loan.current.basis_balance_date)}</dd></div><div><dt>仮定した返済</dt><dd>{loan.current.assumed_payment_count}回</dd></div></>}<div><dt>返済済み元金</dt><dd>{formatYen(repaidPrincipal)}</dd></div><div><dt>元金返済率</dt><dd>{formatPercentage(repaidRatio)}</dd></div><div><dt>現在金利</dt><dd>{formatRate(loan.current.annual_rate)}</dd></div><div><dt>月返済額</dt><dd>{formatYen(loan.current.monthly_payment)}</dd></div><div><dt>当初元金</dt><dd>{formatYen(loan.original_principal)}</dd></div><div><dt>最終返済日</dt><dd>{formatDate(loan.maturity_date)}</dd></div><div><dt>次回見直し</dt><dd>{loan.payment_review.schedule[0] ? formatDate(loan.payment_review.schedule[0]) : "—"}</dd></div><div><dt>見直しルール</dt><dd>{loan.payment_review.rule_verification_status}</dd></div></dl></article>; })}</div></section>

      <section className="section-block forecast-block" aria-labelledby="forecast-heading"><div className="section-heading-row"><div className="section-heading"><p className="section-kicker">Forecast / シナリオ</p><h2 id="forecast-heading">金利仮定ごとの返済リスク</h2><p>Currentは現在金利継続の機械的ケース、その他は手動設定した将来仮定です。銀行予測や確定値ではありません。</p></div><ScopePicker value={scope} data={data} onChange={setScope} /></div><div className="scenario-grid">{scenarios.map((scenario) => { const view = views.get(scenario.id); return view ? <ScenarioCard key={scenario.id} scenario={scenario} view={view} rate={rateAssumption(scenario, data, scope)} /> : null; })}</div></section>

      <section className="section-block charts-block" aria-labelledby="charts-heading"><div className="section-heading-row"><div className="section-heading"><p className="section-kicker">Forecast / Trends</p><h2 id="charts-heading">残高と月返済額の推移</h2><p>{data.presentation.show_trend_charts ? "グラフとデータ表はPythonが計算した時系列を表示しています。" : "データ表はPythonが計算した時系列を表示しています。"} 横軸と表の年齢は、その年に迎える年齢です。上の返済リスクと同じ表示対象に連動します。</p></div><ScopePicker value={scope} data={data} onChange={setScope} label="推移の表示対象" /></div><Suspense fallback={<p>推移データを読み込んでいます</p>}><div className="charts-grid"><ForecastLineChart title="残高推移" description="Current・Base・Higher・Stressの残高を比較" series={balanceSeries} valueLabel="年末残高" ageReferences={ageReferences} showChart={data.presentation.show_trend_charts} /><ForecastLineChart title="月返済額推移" description="5年ごとの見直しを表示" series={paymentSeries} valueLabel="月返済額" ageReferences={ageReferences} showChart={data.presentation.show_trend_charts} /></div></Suspense><ScrollableTable label="125%上限が発動した見直し" className="cap-table"><table><caption>125%上限が発動した見直し</caption><thead><tr><th scope="col">シナリオ</th><th scope="col">ローン</th><th scope="col">見直し日</th><th scope="col">理論額</th><th scope="col">上限額</th><th scope="col">採用額</th></tr></thead><tbody>{capEvents.length ? capEvents.map((event) => <tr key={`${event.scenarioId}-${event.loan_id}-${event.review_date}`}><th scope="row">{event.scenarioId}</th><td>{event.loan_id ?? scope}</td><td>{formatDate(event.review_date)}</td><td>{formatYen(Math.round(event.theoretical_payment))}</td><td>{formatYen(Math.round(event.payment_cap))}</td><td>{formatYen(event.new_payment)} <span className="cap-label">上限発動</span></td></tr>) : <tr><td colSpan={6}>上限発動はありません。</td></tr>}</tbody></table></ScrollableTable></section>

      <section className="section-block sensitivity-block" aria-labelledby="sensitivity-heading"><div className="section-heading"><p className="section-kicker">Mechanical sensitivity</p><h2 id="sensitivity-heading">一定金利の感応度分析</h2><p>経済予測ではなく、同じ金利が満期まで続く機械的な比較です。</p></div><div className="sensitivity-layout"><Suspense fallback={<p>感応度グラフを読み込んでいます</p>}><SensitivityChart cases={sensitivity} /></Suspense><ScrollableTable label="一定金利ごとの返済リスク"><table><caption>一定金利ごとの返済リスク</caption><thead><tr><th scope="col">金利</th><th scope="col">最大月返済</th><th scope="col">上限発動</th><th scope="col">未払利息</th><th scope="col">最大未払</th><th scope="col">最終返済</th><th scope="col">追加最終返済</th><th scope="col">計算仮定</th><th scope="col">総支払利息</th><th className="remarks-cell" scope="col">備考</th></tr></thead><tbody>{sensitivity.map((item) => { const hasUnverified = item.warnings.some((warning) => warning.verification_status === "unverified"); const remarks = [...new Set([
        currentRates.has(item.annual_rate) ? "現在金利" : null,
        [0.03, 0.04, 0.05].includes(item.annual_rate) ? "主要比較金利" : null,
        item.payment_cap_trigger_count > 0 ? "125%上限発動" : null,
        item.unpaid_interest_ever_occurred ? "未払利息発生" : null,
        item.extra_final_payment > 0 ? "追加最終返済あり" : null,
      ].filter((remark): remark is string => remark !== null))]; return <tr key={item.annual_rate}><th scope="row">{formatRate(item.annual_rate)}</th><td>{formatYen(item.maximum_monthly_payment)}</td><td>{item.payment_cap_trigger_count}回</td><td>{item.unpaid_interest_ever_occurred ? `あり（${item.first_unpaid_interest_date ? formatDate(item.first_unpaid_interest_date) : "日付不明"}）` : "なし"}</td><td>{formatYen(item.maximum_unpaid_interest)}</td><td>{formatYen(item.final_payment)}</td><td>{formatYen(item.extra_final_payment)}</td><td>{hasUnverified ? <span className="table-warning">未検証仮定あり</span> : "—"}</td><td>{formatYen(item.total_interest_paid)}</td><td className="remarks-cell">{remarks.length > 0 ? remarks.join("・") : "—"}</td></tr>; })}</tbody></table></ScrollableTable></div></section>

      <section className="section-block status-block" aria-labelledby="status-heading"><div className="section-heading"><p className="section-kicker">Model status</p><h2 id="status-heading">計算モデルの検証状態</h2><p>実績との0円一致は過去期間の再現結果です。将来シナリオの正確さや金利予測を意味しません。</p></div><div className="status-layout"><article className="status-summary"><p className="status-pass">{data.model_status.golden_tests_passed ? "Golden tests validated" : "Golden tests not validated"}</p><strong>実績再現最大誤差: {formatYen(data.model_status.maximum_balance_error_yen)}</strong><dl className="data-list"><div><dt>検証期間</dt><dd>{data.model_status.validated_actual_period_start && data.model_status.validated_actual_period_end ? `${formatDate(data.model_status.validated_actual_period_start)}〜${formatDate(data.model_status.validated_actual_period_end)}` : "—"}</dd></div><div><dt>最新実績日</dt><dd>{data.model_status.latest_actual_date ? formatDate(data.model_status.latest_actual_date) : "—"}</dd></div><div><dt>未検証ルール</dt><dd>{data.model_status.unverified_rule_count}件</dd></div><div><dt>Schema</dt><dd>v{data.schema_version}</dd></div></dl></article><div className="validation-list">{data.loans.map((loan) => <article key={loan.id}><h3>{loan.display_name}</h3><p>{loan.actual_validation.period_start && loan.actual_validation.period_end ? `${formatDate(loan.actual_validation.period_start)}〜${formatDate(loan.actual_validation.period_end)}` : "期間なし"}</p><p><strong>{loan.actual_validation.validated_payment_count}か月検証済み</strong> · 最大誤差 {formatYen(loan.actual_validation.maximum_balance_error_yen)}</p><p>付利残高単位: <strong>{formatYen(loan.interest_calculation.balance_unit_yen)}</strong>（銀行返済予定表の実績から推定）</p></article>)}</div></div></section>

      <section className="section-block assumptions-block" aria-labelledby="assumptions-heading"><div className="section-heading"><p className="section-kicker">Warnings / assumptions</p><h2 id="assumptions-heading">モデル上の注意と前提</h2><p>severityはモデル仕様やデータ品質に関する表示で、家計の危険度判定ではありません。</p></div><ul className="warning-list">{groupedWarnings.map((warning) => <li key={warning.code}><span className={`severity severity-${warning.severity}`}>{warning.severity}</span><div><strong>{warningText(warning)}</strong><p>{warning.code} · {warning.verification_status}</p></div></li>)}</ul></section>

      <section className="section-block sources-block" aria-labelledby="sources-heading"><div className="section-heading"><p className="section-kicker">Sources</p><h2 id="sources-heading">根拠・前提</h2></div><div className="source-list">{data.sources.map((source) => <article key={source.id}><div><span className="status-chip">{source.type}</span><h3>{source.description}</h3><p>{source.publisher} · 取得日 {formatDate(source.retrieved_at)}</p></div>{source.url && <a href={source.url} target="_blank" rel="noreferrer">公式資料を開く<span className="sr-only">（新しいタブ）</span></a>}</article>)}</div></section>
    </main>
    <footer><p>このダッシュボードは住宅ローン返済条件のシミュレーションであり、金融アドバイスではありません。将来金利や返済額を保証するものではありません。</p><p>{isSample ? "表示している金額・日付・契約条件はすべて公開デモ用の人工データです。" : "個人の住宅ローン情報を含むローカル専用画面です。公開デプロイしないでください。"}</p></footer>
  </>;
}

export default function App() {
  const [data, setData] = useState<ForecastDocument | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { loadForecast().then(setData).catch(() => setError(true)); }, []);
  if (error) return <main className="state-message"><h1>住宅ローンデータを読み込めませんでした。</h1><p>forecast.jsonを生成済みか確認してください。</p></main>;
  if (!data) return <main className="state-message"><p>データを読み込んでいます</p></main>;
  return <Dashboard data={data} />;
}
