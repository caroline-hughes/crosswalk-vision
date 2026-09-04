import type { CrosswalkRecord } from "@crosswalks/contracts";

export const BOROUGHS = [
  "Manhattan",
  "Bronx",
  "Brooklyn",
  "Queens",
  "Staten Island"
] as const;

export type BoroughName = (typeof BOROUGHS)[number];

export interface MapFilters {
  borough: "all" | BoroughName;
  nearSchool: boolean;
  has311: boolean;
  minModelScore: number;
}

export const DEFAULT_FILTERS: MapFilters = {
  borough: "all",
  nearSchool: false,
  has311: false,
  minModelScore: 0
};

export function applyFilters(records: CrosswalkRecord[], filters: MapFilters): CrosswalkRecord[] {
  return records.filter((record) => {
    if (filters.borough !== "all" && record.borough !== filters.borough) {
      return false;
    }
    if (filters.nearSchool && !record.school_zone) {
      return false;
    }
    if (filters.has311 && record.pavement_marking_311_count_since_2020 <= 0) {
      return false;
    }
    if (record.model_score < filters.minModelScore) {
      return false;
    }
    return true;
  });
}

/** Sequential amber → #FF4F00 → vermillion stops for priority within the plotted set. */
const PRIORITY_STOPS: Array<{ t: number; rgb: [number, number, number] }> = [
  { t: 0, rgb: [214, 168, 90] },
  { t: 0.42, rgb: [255, 79, 0] },
  { t: 1, rgb: [148, 18, 18] }
];

export function scoreUnit(score: number, minScore: number, maxScore: number): number {
  if (!Number.isFinite(score) || !Number.isFinite(minScore) || !Number.isFinite(maxScore)) {
    return 0.5;
  }
  if (maxScore <= minScore) {
    return 1;
  }
  return Math.min(1, Math.max(0, (score - minScore) / (maxScore - minScore)));
}

function mixChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

export function scoreColor(score: number, minScore: number, maxScore: number): string {
  const unit = scoreUnit(score, minScore, maxScore);
  let lower = PRIORITY_STOPS[0];
  let upper = PRIORITY_STOPS[PRIORITY_STOPS.length - 1];
  for (let index = 0; index < PRIORITY_STOPS.length - 1; index += 1) {
    const current = PRIORITY_STOPS[index];
    const next = PRIORITY_STOPS[index + 1];
    if (unit >= current.t && unit <= next.t) {
      lower = current;
      upper = next;
      break;
    }
  }
  const span = upper.t - lower.t || 1;
  const local = (unit - lower.t) / span;
  const r = mixChannel(lower.rgb[0], upper.rgb[0], local);
  const g = mixChannel(lower.rgb[1], upper.rgb[1], local);
  const b = mixChannel(lower.rgb[2], upper.rgb[2], local);
  return `rgb(${r}, ${g}, ${b})`;
}

export function scoreMarkerSize(score: number, minScore: number, maxScore: number): number {
  return Math.round(30 + scoreUnit(score, minScore, maxScore) * 16);
}
