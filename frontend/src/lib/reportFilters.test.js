import {
  REPORT_MIN_DATE, clampReportDate, defaultReportRange, filterReportChannels,
  productExportParams, reportCoverageDays, reportPresetRange, splitReportRange,
} from "./reportFilters";

test("report range starts at the historical reporting boundary", () => {
  expect(defaultReportRange(new Date(2026, 8, 7))).toEqual({ from: REPORT_MIN_DATE, to: "2026-09-07" });
  expect(clampReportDate("2025-01-01")).toBe(REPORT_MIN_DATE);
  expect(reportCoverageDays(new Date(2026, 8, 7))).toBe(95);
});

test("long Trendyol reconciliation periods are split without gaps", () => {
  expect(splitReportRange("2026-06-05", "2026-09-07", 31)).toEqual([
    { from: "2026-06-05", to: "2026-07-05" },
    { from: "2026-07-06", to: "2026-08-05" },
    { from: "2026-08-06", to: "2026-09-05" },
    { from: "2026-09-06", to: "2026-09-07" },
  ]);
});

test("presets are inclusive and never cross the reporting boundary", () => {
  expect(reportPresetRange("7", new Date(2026, 8, 7))).toEqual({ from: "2026-09-01", to: "2026-09-07" });
  expect(reportPresetRange("365", new Date(2026, 8, 7))).toEqual({ from: REPORT_MIN_DATE, to: "2026-09-07" });
});

test("channel table follows the selected report source", () => {
  const rows = [{ source: "Site" }, { source: "Trendyol" }];
  expect(filterReportChannels(rows, "site")).toEqual([{ source: "Site" }]);
  expect(filterReportChannels(rows, "trendyol")).toEqual([{ source: "Trendyol" }]);
  expect(filterReportChannels(rows, "all")).toEqual(rows);
});

test("product export carries every visible table filter", () => {
  const params = productExportParams({
    from: "2026-06-05", to: "2026-09-07", platform: "trendyol", size: "M",
    season: "Yaz", velocity: "green", query: "bermuda", sortKey: "revenue", sortDir: "desc",
  });
  expect(Object.fromEntries(params)).toEqual({
    start_date: "2026-06-05", end_date: "2026-09-07T23:59:59", source: "trendyol",
    platform: "trendyol", size: "M", season: "Yaz", velocity: "green", q: "bermuda",
    sort_by: "revenue", sort_dir: "desc",
  });
});
