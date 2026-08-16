import { readFile } from "node:fs/promises";
import { validateForecastForBuild } from "./forecast-build-policy.mjs";

try {
  const contents = await readFile(
    new URL("../public/generated/forecast.json", import.meta.url),
    "utf8",
  );
  validateForecastForBuild(
    JSON.parse(contents),
    process.env.MORTGAGE_ALLOW_EXTERNAL_BUILD,
  );
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error("リポジトリのルートで python scripts/generate_forecast.py を実行してください。");
  process.exit(1);
}
