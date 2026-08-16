export const formatYen = (value: number): string =>
  `${new Intl.NumberFormat("ja-JP").format(value)}円`;

export const formatTenThousandYen = (value: number): string =>
  `${new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 1 }).format(value / 10_000)}万円`;

export const formatDate = (value: string): string =>
  new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Tokyo",
  }).format(new Date(`${value}T00:00:00+09:00`));

export const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat("ja-JP", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

export const formatRate = (value: number): string =>
  `${new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 3 }).format(value * 100)}%`;

export const formatMonth = (value: string): string => {
  const [year, month] = value.slice(0, 7).split("-").map(Number);
  return `${year}年${month}月`;
};
