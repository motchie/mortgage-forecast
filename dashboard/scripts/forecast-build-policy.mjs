export const EXTERNAL_BUILD_ACKNOWLEDGEMENT = "I_UNDERSTAND";

export function validateForecastForBuild(document, acknowledgement) {
  const sourceType = document?.data_source?.type;
  if (sourceType !== "sample" && sourceType !== "external") {
    throw new Error("forecast.json の data_source.type が不正です。再生成してください。");
  }
  if (
    sourceType === "external" &&
    acknowledgement !== EXTERNAL_BUILD_ACKNOWLEDGEMENT
  ) {
    throw new Error(
      "external dataを含むforecastは通常buildできません。ローカルまたは認証済み環境専用と確認した場合のみ " +
      `MORTGAGE_ALLOW_EXTERNAL_BUILD=${EXTERNAL_BUILD_ACKNOWLEDGEMENT} を明示してください。`,
    );
  }
}
