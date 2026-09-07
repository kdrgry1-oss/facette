export const REPORT_MIN_DATE = "2026-06-05";

export const localYmd = (date) => {
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const clampReportDate = (value) => {
  const date = String(value || "").slice(0, 10);
  return date && date < REPORT_MIN_DATE ? REPORT_MIN_DATE : date;
};

export function defaultReportRange(today = new Date()) {
  return { from: REPORT_MIN_DATE, to: localYmd(today) };
}

export function reportCoverageDays(today = new Date()) {
  const start = new Date(`${REPORT_MIN_DATE}T12:00:00`);
  const end = new Date(`${localYmd(today)}T12:00:00`);
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}

export function splitReportRange(from, to, maxDays = 31) {
  const start = new Date(`${clampReportDate(from)}T12:00:00`);
  const finish = new Date(`${clampReportDate(to)}T12:00:00`);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(finish.getTime()) || start > finish) return [];
  const size = Math.max(1, Number(maxDays) || 31);
  const chunks = [];
  for (let cursor = start; cursor <= finish;) {
    const end = new Date(cursor);
    end.setDate(end.getDate() + size - 1);
    if (end > finish) end.setTime(finish.getTime());
    chunks.push({ from: localYmd(cursor), to: localYmd(end) });
    cursor = new Date(end);
    cursor.setDate(cursor.getDate() + 1);
  }
  return chunks;
}

export function reportPresetRange(key, today = new Date()) {
  const end = localYmd(today);
  let from = end;
  if (key === "yesterday") {
    const yesterday = localYmd(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1));
    return { from: clampReportDate(yesterday), to: clampReportDate(yesterday) };
  }
  if (key === "thismonth" || key === "month") {
    from = localYmd(new Date(today.getFullYear(), today.getMonth(), 1));
  } else {
    const days = Math.max(1, Number(key) || 1);
    from = localYmd(new Date(today.getFullYear(), today.getMonth(), today.getDate() - (days - 1)));
  }
  return { from: clampReportDate(from), to: end };
}

export function filterReportChannels(items, source) {
  if (!source || source === "all") return items || [];
  const wanted = source === "site" ? "site" : source.toLocaleLowerCase("tr");
  return (items || []).filter((row) => {
    const value = String(row?.source || row?.channel || "").trim().toLocaleLowerCase("tr");
    return wanted === "site" ? ["site", "facette", "site (kendi)"].includes(value) : value === wanted;
  });
}

export function productExportParams({ from, to, platform, size, season, velocity, query, sortKey, sortDir }) {
  const params = new URLSearchParams({
    start_date: clampReportDate(from),
    end_date: `${clampReportDate(to)}T23:59:59`,
  });
  if (platform) {
    params.set("source", platform);
    params.set("platform", platform);
  }
  if (size) params.set("size", size);
  if (season) params.set("season", season);
  if (velocity) params.set("velocity", velocity);
  if (query?.trim()) params.set("q", query.trim());
  if (sortKey) params.set("sort_by", sortKey);
  if (sortDir) params.set("sort_dir", sortDir);
  return params;
}
