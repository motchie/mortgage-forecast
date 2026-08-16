import { describe, expect, it } from "vitest";
import { formatDate, formatPercentage, formatRate, formatTenThousandYen, formatYen } from "../formatters";

describe("表示フォーマット", () => {
  it("円、金利、日付を日本語表示する", () => {
    expect(formatYen(14_000_000)).toBe("14,000,000円");
    expect(formatTenThousandYen(26_000_000)).toBe("2,600万円");
    expect(formatTenThousandYen(100_000)).toBe("10万円");
    expect(formatRate(0.0175)).toBe("1.75%");
    expect(formatPercentage(0.276)).toBe("27.6%");
    expect(formatDate("2026-09-11")).toBe("2026年9月11日");
  });
});
