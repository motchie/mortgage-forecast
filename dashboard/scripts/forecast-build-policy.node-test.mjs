import assert from "node:assert/strict";
import test from "node:test";

import {
  EXTERNAL_BUILD_ACKNOWLEDGEMENT,
  validateForecastForBuild,
} from "./forecast-build-policy.mjs";

test("sample forecast is accepted", () => {
  assert.doesNotThrow(() => validateForecastForBuild({ data_source: { type: "sample" } }));
});

test("external forecast is rejected without explicit acknowledgement", () => {
  assert.throws(
    () => validateForecastForBuild({ data_source: { type: "external" } }),
    /external data/,
  );
});

test("external forecast can be built only with exact acknowledgement", () => {
  assert.doesNotThrow(() =>
    validateForecastForBuild(
      { data_source: { type: "external" } },
      EXTERNAL_BUILD_ACKNOWLEDGEMENT,
    ),
  );
});
