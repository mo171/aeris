// lib/formatters.ts — the single set of display formatters. No component formats a value inline.
//
// what  : Byte sizes, relative times, geographic coordinates, percentages and durations, formatted the
//         AERIS way.
// where : Used by any component that renders a number or a date.
// how   : Centralised so the same value never appears in two different formats on two different screens —
//         "14.2 ha" on one panel and "14.20 hectares" on another erodes trust in the numbers themselves.
//         Coordinates use the sexagesimal-free decimal form with an explicit hemisphere letter, which is
//         what a geospatial analyst expects to be able to copy straight into another tool.

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"] as const;
const BYTES_PER_UNIT = 1024;

export function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return "0 B";
  }

  const unitIndex = Math.min(
    BYTE_UNITS.length - 1,
    Math.floor(Math.log(bytes) / Math.log(BYTES_PER_UNIT)),
  );
  const value = bytes / Math.pow(BYTES_PER_UNIT, unitIndex);

  return `${value >= 100 || unitIndex === 0 ? Math.round(value) : value.toFixed(1)} ${BYTE_UNITS[unitIndex]}`;
}

const RELATIVE_TIME_UNITS: readonly { unit: Intl.RelativeTimeFormatUnit; ms: number }[] = [
  { unit: "year", ms: 365 * 24 * 3_600_000 },
  { unit: "month", ms: 30 * 24 * 3_600_000 },
  { unit: "day", ms: 24 * 3_600_000 },
  { unit: "hour", ms: 3_600_000 },
  { unit: "minute", ms: 60_000 },
];

const relativeTimeFormatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function formatRelativeTime(isoTimestamp: string, now: number = Date.now()): string {
  const timestamp = Date.parse(isoTimestamp);
  if (Number.isNaN(timestamp)) {
    return "unknown";
  }

  const deltaMs = timestamp - now;
  const absoluteDeltaMs = Math.abs(deltaMs);

  for (const { unit, ms } of RELATIVE_TIME_UNITS) {
    if (absoluteDeltaMs >= ms) {
      return relativeTimeFormatter.format(Math.round(deltaMs / ms), unit);
    }
  }

  return "just now";
}

export function formatAbsoluteDate(isoTimestamp: string): string {
  const timestamp = Date.parse(isoTimestamp);
  if (Number.isNaN(timestamp)) {
    return "unknown";
  }
  return new Date(timestamp).toISOString().slice(0, 10);
}

export function formatCoordinates(latitude: number, longitude: number): string {
  const latitudeHemisphere = latitude >= 0 ? "N" : "S";
  const longitudeHemisphere = longitude >= 0 ? "E" : "W";

  return `${Math.abs(latitude).toFixed(3)}°${latitudeHemisphere} ${Math.abs(longitude).toFixed(3)}°${longitudeHemisphere}`;
}

export function formatPercentage(value: number, fractionDigits = 0): string {
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatDurationMs(durationMs: number): string {
  if (durationMs < 1_000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1_000).toFixed(durationMs < 10_000 ? 2 : 1)} s`;
}

export function formatGroundSampleDistance(meters: number): string {
  return meters < 1 ? `${(meters * 100).toFixed(0)} cm` : `${meters} m`;
}
