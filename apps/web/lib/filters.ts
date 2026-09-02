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

export function heatClass(score: number): "blaze" | "hot" | "warm" | "cool" {
  if (score >= 0.72) {
    return "blaze";
  }
  if (score >= 0.6) {
    return "hot";
  }
  if (score >= 0.48) {
    return "warm";
  }
  return "cool";
}
