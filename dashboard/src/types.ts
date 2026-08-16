export type VerificationStatus = "actual" | "contractual" | "official_product_rule" | "inferred" | "scenario" | "unverified";
export type WarningSeverity = "info" | "warning" | "critical";

export interface ModelWarning {
  code: string;
  severity: WarningSeverity;
  scope: { loan_id: string; scenario_id: string };
  message: string;
  verification_status: VerificationStatus;
  source_ids: string[];
}

export interface ActualValidation {
  period_start: string | null;
  period_end: string | null;
  validated_payment_count: number;
  maximum_balance_error_yen: number;
  verification_status: VerificationStatus;
}

export interface Loan {
  id: string;
  display_name: string;
  original_principal: number;
  disbursement_date: string;
  maturity_date: string;
  current: { balance: number; balance_date: string; annual_rate: number; monthly_payment: number; verification_status: VerificationStatus };
  repayment: { method: string; payment_day: number; bonus_payment: boolean };
  payment_review: { schedule: string[]; rule_verification_status: VerificationStatus; source_ids: string[] };
  rate_model: { type: string; spread: number; verification_status: VerificationStatus; source_ids: string[] };
  interest_calculation: { balance_unit_yen: number; verification_status: VerificationStatus; source_ids: string[] };
  actual_validation: ActualValidation;
}

export interface ReviewSummary { date: string; expected_payment: number; theoretical_payment: number; payment_cap: number; cap_triggered: boolean }
export interface ReviewEvent {
  loan_id?: string;
  review_date: string;
  previous_payment: number;
  theoretical_payment: number;
  payment_cap: number;
  new_payment: number;
  cap_triggered: boolean;
  cap_rounding_verification_status: string;
  unpaid_interest_review_verification_status: string;
}
export interface UnpaidInterestSummary { ever_occurred: boolean; first_date: string | null; resolved_date: string | null; maximum_amount: number; amount_at_maturity: number }
export interface BalancePoint { date: string; balance: number }
export interface PaymentPoint { date: string; monthly_payment: number; payment_type: "scheduled" | "final"; scenario_id: string; loan_id: string }

export interface ScenarioResult {
  scenario_id: string;
  loan_id: string;
  starting_date: string;
  starting_balance: number;
  next_payment_review: ReviewSummary | null;
  maximum_monthly_payment: number;
  payment_cap_trigger_count: number;
  payment_cap_events: ReviewEvent[];
  unpaid_interest: UnpaidInterestSummary;
  remaining_principal_at_maturity: number;
  final_payment: number;
  extra_final_payment: number;
  total_interest_paid: number;
  warnings: ModelWarning[];
  verification_status: VerificationStatus;
  chart_data: { balance_series: BalancePoint[]; payment_series: PaymentPoint[]; annual_interest: Array<{ year: number; interest_paid: number }> };
}

export interface ScenarioRatePoint { effective_date: string; annual_rate: number }
export interface Scenario {
  id: string;
  label: string;
  type: string;
  description: string;
  updated_at: string;
  verification_status: VerificationStatus;
  annual_rate?: number | null;
  rate_source?: string;
  rates?: ScenarioRatePoint[];
  terminal_rate?: number | null;
  results: ScenarioResult[];
}
export interface CombinedScenario {
  scenario_id: string;
  monthly_combined_payment_series: Array<{ month: string; payment: number }>;
  monthly_combined_balance_series: Array<{ month: string; balance: number }>;
  maximum_combined_monthly_payment: number;
  combined_final_payment: number;
  combined_extra_final_payment: number;
  combined_remaining_principal_at_maturity: number;
  combined_remaining_unpaid_interest_at_maturity: number;
  combined_total_interest_paid: number;
  next_payment_review: ReviewSummary | null;
  payment_cap_trigger_count: number;
  payment_cap_events: ReviewEvent[];
  unpaid_interest: UnpaidInterestSummary;
  warnings: ModelWarning[];
}
export interface SensitivityCase {
  annual_rate: number;
  maximum_monthly_payment: number;
  payment_cap_trigger_count: number;
  unpaid_interest_ever_occurred: boolean;
  first_unpaid_interest_date: string | null;
  unpaid_interest_resolved_date: string | null;
  maximum_unpaid_interest: number;
  remaining_principal_at_maturity: number;
  remaining_unpaid_interest_at_maturity: number;
  final_payment: number;
  extra_final_payment: number;
  total_interest_paid: number;
  warnings: ModelWarning[];
}
export interface Source { id: string; publisher: string; type: VerificationStatus; description: string; retrieved_at: string; url?: string }

export interface ForecastDocument {
  schema_version: string;
  data_source: { type: "sample" | "external" };
  presentation: { show_trend_charts: boolean };
  generated_at: string;
  model_status: {
    golden_tests_passed: boolean;
    validated_actual_period_start: string | null;
    validated_actual_period_end: string | null;
    maximum_balance_error_yen: number;
    latest_actual_date: string | null;
    latest_actual_balance: number | null;
    calculation_engine_version: string;
    unverified_rule_count: number;
  };
  loans: Loan[];
  combined: { current_balance: number; current_monthly_payment: number; scenarios: CombinedScenario[]; sensitivity: SensitivityCase[] };
  scenarios: Scenario[];
  sensitivity: Array<{ loan_id: string; cases: SensitivityCase[] }>;
  sources: Source[];
  warnings: ModelWarning[];
}
