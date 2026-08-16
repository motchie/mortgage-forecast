import type {
  CombinedScenario,
  ForecastDocument,
  ModelWarning,
  Scenario,
  ScenarioResult,
  SensitivityCase,
} from "../types";

const warning: ModelWarning = {
  code: "UNVERIFIED_FINAL_PAYMENT",
  severity: "warning",
  scope: { loan_id: "example-loan", scenario_id: "stress" },
  message: "Artificial warning for frontend tests",
  verification_status: "unverified",
  source_ids: ["example-unverified-rule"],
};

const unpaid = {
  ever_occurred: false,
  first_date: null,
  resolved_date: null,
  maximum_amount: 0,
  amount_at_maturity: 0,
};

function result(scenarioId: string): ScenarioResult {
  return {
    scenario_id: scenarioId,
    loan_id: "example-loan",
    starting_date: "2026-08-20",
    starting_balance: 14_000_000,
    next_payment_review: null,
    maximum_monthly_payment: 65_000,
    payment_cap_trigger_count: 0,
    payment_cap_events: [],
    unpaid_interest: unpaid,
    remaining_principal_at_maturity: 0,
    final_payment: 40_000,
    extra_final_payment: 0,
    total_interest_paid: 2_000_000,
    warnings: scenarioId === "stress" ? [warning] : [],
    verification_status: "scenario",
    chart_data: {
      balance_series: [
        { date: "2026-08-20", balance: 14_000_000 },
        { date: "2027-08-20", balance: 13_500_000 },
      ],
      payment_series: [
        {
          date: "2026-09-20",
          monthly_payment: 65_000,
          payment_type: "scheduled",
          scenario_id: scenarioId,
          loan_id: "example-loan",
        },
      ],
      annual_interest: [{ year: 2027, interest_paid: 200_000 }],
    },
  };
}

function combined(scenarioId: string): CombinedScenario {
  const loanResult = result(scenarioId);
  return {
    scenario_id: scenarioId,
    monthly_combined_payment_series: [{ month: "2026-09", payment: 65_000 }],
    monthly_combined_balance_series: [{ month: "2026-09", balance: 13_956_000 }],
    maximum_combined_monthly_payment: 65_000,
    combined_final_payment: 40_000,
    combined_extra_final_payment: 0,
    combined_remaining_principal_at_maturity: 0,
    combined_remaining_unpaid_interest_at_maturity: 0,
    combined_total_interest_paid: 2_000_000,
    next_payment_review: null,
    payment_cap_trigger_count: 0,
    payment_cap_events: [],
    unpaid_interest: unpaid,
    warnings: loanResult.warnings,
  };
}

function sensitivity(annualRate: number): SensitivityCase {
  return {
    annual_rate: annualRate,
    maximum_monthly_payment: 65_000,
    payment_cap_trigger_count: 0,
    unpaid_interest_ever_occurred: false,
    first_unpaid_interest_date: null,
    unpaid_interest_resolved_date: null,
    maximum_unpaid_interest: 0,
    remaining_principal_at_maturity: 0,
    remaining_unpaid_interest_at_maturity: 0,
    final_payment: 40_000,
    extra_final_payment: annualRate === 0.05 ? 100_000 : 0,
    total_interest_paid: 2_000_000,
    warnings: annualRate === 0.05 ? [warning] : [],
  };
}

const scenarioMetadata = [
  ["current", "Current"],
  ["base", "Base"],
  ["higher", "Higher"],
  ["stress", "Stress"],
] as const;

const scenarios: Scenario[] = scenarioMetadata.map(([id, label]) => ({
  id,
  label,
  type: id === "current" ? "constant_loan_rate" : "loan_rate_path",
  description: `Artificial ${label} scenario`,
  updated_at: "2026-08-15",
  verification_status: "scenario",
  results: [result(id)],
}));

const sensitivityCases = [0.018, 0.03, 0.04, 0.05].map(sensitivity);

const forecastFixture: ForecastDocument = {
  schema_version: "1.0",
  data_source: { type: "sample" },
  generated_at: "2026-08-15T12:00:00+09:00",
  model_status: {
    golden_tests_passed: true,
    validated_actual_period_start: "2026-09-20",
    validated_actual_period_end: "2026-12-20",
    maximum_balance_error_yen: 0,
    latest_actual_date: "2026-12-20",
    latest_actual_balance: 13_823_602,
    calculation_engine_version: "0.1.0",
    unverified_rule_count: 1,
  },
  loans: [
    {
      id: "example-loan",
      display_name: "Example variable-rate loan",
      original_principal: 20_000_000,
      disbursement_date: "2020-04-20",
      maturity_date: "2045-04-20",
      current: {
        balance: 14_000_000,
        balance_date: "2026-08-20",
        annual_rate: 0.018,
        monthly_payment: 65_000,
        verification_status: "actual",
      },
      repayment: { method: "equal_payment", payment_day: 20, bonus_payment: false },
      payment_review: {
        schedule: ["2030-04-20"],
        rule_verification_status: "contractual",
        source_ids: ["example-payment-review"],
      },
      rate_model: {
        type: "short_prime_spread",
        spread: -0.005,
        verification_status: "scenario",
        source_ids: ["example-rate-model"],
      },
      interest_calculation: {
        balance_unit_yen: 1,
        verification_status: "contractual",
        source_ids: ["example-interest-rule"],
      },
      actual_validation: {
        period_start: "2026-09-20",
        period_end: "2026-12-20",
        validated_payment_count: 4,
        maximum_balance_error_yen: 0,
        verification_status: "actual",
      },
    },
  ],
  combined: {
    current_balance: 14_000_000,
    current_monthly_payment: 65_000,
    scenarios: scenarioMetadata.map(([id]) => combined(id)),
    sensitivity: sensitivityCases,
  },
  scenarios,
  sensitivity: [{ loan_id: "example-loan", cases: sensitivityCases }],
  sources: [
    {
      id: "example-source",
      publisher: "Example Lender",
      type: "actual",
      description: "Artificial frontend test source",
      retrieved_at: "2026-08-15",
    },
  ],
  warnings: [warning],
};

export default forecastFixture;
