import type { ForecastDocument } from "./types";

export function parseForecast(value: unknown): ForecastDocument {
  if (!value || typeof value !== "object") throw new Error("invalid forecast");
  const candidate = value as Partial<ForecastDocument>;
  if (candidate.schema_version !== "1.0" || !Array.isArray(candidate.loans) || !Array.isArray(candidate.scenarios) || !candidate.combined || !candidate.model_status) {
    throw new Error("forecast schema mismatch");
  }
  return candidate as ForecastDocument;
}

export async function loadForecast(): Promise<ForecastDocument> {
  const response = await fetch("/generated/forecast.json");
  if (!response.ok) throw new Error("forecast fetch failed");
  return parseForecast(await response.json());
}
