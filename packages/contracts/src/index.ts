export type ReasonTag =
  | "low contrast"
  | "broken stripes"
  | "partial paint loss"
  | "school zone"
  | `311 x${number} since 2020`
  | string;

export interface Matched311Complaint {
  unique_key: string;
  created_date: string;
  descriptor: string;
  incident_address: string;
  url: string;
}

export interface ModelFeatureContribution {
  feature: string;
  label: string;
  contribution: number;
  direction: string;
}

export interface CrosswalkRecord {
  id: string;
  intersection_label: string;
  leg_label: string;
  lat: number;
  lon: number;
  year: 2024;
  severity_score: number;
  confidence_score: number;
  rank_score: number;
  reason_tags: ReasonTag[];
  school_zone: boolean;
  pavement_marking_311_count_since_2020: number;
  matched_311_complaints: Matched311Complaint[];
  image_url: string;
  thumbnail_url: string;
  google_maps_url: string;
  model_score: number;
  heuristic_score: number;
  neighborhood: string;
  neighborhood_id: string;
  borough: string;
  priority_reason: string;
  pedestrian_crash_count: number;
  top_features: ModelFeatureContribution[];
}

export interface CrosswalkMeta {
  build_timestamp: string;
  source_versions: {
    imagery: string;
    lion: string;
    service_requests_311: string;
    school_zones: string;
    vision_zero_crashes: string;
    neighborhoods: string;
  };
  pilot_boundary: string;
  total_records: number;
  scoring_method: string;
  label_definition: string;
  eval_split?: string;
  eval_n?: number | null;
  eval_n_pos?: number | null;
  eval_learned_auc?: number | null;
  eval_heuristic_auc?: number | null;
  eval_learned_ap?: number | null;
  eval_learned_precision_at_5?: number | null;
  showcase_top_k?: number;
  n_scored?: number;
  n_plotted?: number;
  plot_percentile?: number;
  plot_threshold?: number | null;
  plot_rule?: string;
  geography?: string;
  include_image_feature?: boolean;
  include_311_feature?: boolean;
  n_with_imagery?: number;
  imagery_year?: number;
  imagery_rule?: string;
  product_claim: string;
  caveat: string;
}

export function validateCrosswalkRecords(input: unknown): CrosswalkRecord[] {
  if (!Array.isArray(input)) {
    throw new Error("Crosswalk snapshot must be an array.");
  }

  return input.map((entry, index) => validateCrosswalkRecord(entry, index));
}

export function validateCrosswalkMeta(input: unknown): CrosswalkMeta {
  if (!input || typeof input !== "object") {
    throw new Error("Crosswalk meta must be an object.");
  }

  const value = input as Record<string, unknown>;
  const versions = (value.source_versions as Record<string, unknown>) || {};

  return {
    build_timestamp: mustBeString(value.build_timestamp, "build_timestamp"),
    source_versions: {
      imagery: mustBeString(versions.imagery, "source_versions.imagery"),
      lion: mustBeString(versions.lion, "source_versions.lion"),
      service_requests_311: mustBeString(versions.service_requests_311, "source_versions.service_requests_311"),
      school_zones: mustBeString(versions.school_zones, "source_versions.school_zones"),
      vision_zero_crashes: mustBeString(versions.vision_zero_crashes, "source_versions.vision_zero_crashes"),
      neighborhoods: mustBeString(versions.neighborhoods, "source_versions.neighborhoods")
    },
    pilot_boundary: mustBeString(value.pilot_boundary, "pilot_boundary"),
    total_records: mustBeNumber(value.total_records, "total_records"),
    scoring_method: mustBeString(value.scoring_method, "scoring_method"),
    label_definition: mustBeString(value.label_definition, "label_definition"),
    eval_split: optionalString(value.eval_split),
    eval_n: optionalNumber(value.eval_n),
    eval_n_pos: optionalNumber(value.eval_n_pos),
    eval_learned_auc: optionalNumber(value.eval_learned_auc),
    eval_heuristic_auc: optionalNumber(value.eval_heuristic_auc),
    eval_learned_ap: optionalNumber(value.eval_learned_ap),
    eval_learned_precision_at_5: optionalNumber(value.eval_learned_precision_at_5),
    showcase_top_k: optionalNumber(value.showcase_top_k),
    n_scored: optionalNumber(value.n_scored),
    n_plotted: optionalNumber(value.n_plotted),
    plot_percentile: optionalNumber(value.plot_percentile),
    plot_threshold: optionalNumber(value.plot_threshold),
    plot_rule: optionalString(value.plot_rule),
    geography: optionalString(value.geography),
    include_image_feature: typeof value.include_image_feature === "boolean" ? value.include_image_feature : undefined,
    include_311_feature: typeof value.include_311_feature === "boolean" ? value.include_311_feature : undefined,
    n_with_imagery: optionalNumber(value.n_with_imagery),
    imagery_year: optionalNumber(value.imagery_year),
    imagery_rule: optionalString(value.imagery_rule),
    product_claim: mustBeString(value.product_claim, "product_claim"),
    caveat: mustBeString(value.caveat, "caveat")
  };
}

function validateCrosswalkRecord(input: unknown, index: number): CrosswalkRecord {
  if (!input || typeof input !== "object") {
    throw new Error(`Crosswalk record at index ${index} must be an object.`);
  }

  const value = input as Record<string, unknown>;

  return {
    id: mustBeString(value.id, "id"),
    intersection_label: mustBeString(value.intersection_label, "intersection_label"),
    leg_label: mustBeString(value.leg_label, "leg_label"),
    lat: mustBeNumber(value.lat, "lat"),
    lon: mustBeNumber(value.lon, "lon"),
    year: mustBeYear(value.year),
    severity_score: mustBeNumber(value.severity_score, "severity_score"),
    confidence_score: mustBeNumber(value.confidence_score, "confidence_score"),
    rank_score: mustBeNumber(value.rank_score, "rank_score"),
    reason_tags: mustBeStringArray(value.reason_tags, "reason_tags") as ReasonTag[],
    school_zone: mustBeBoolean(value.school_zone, "school_zone"),
    pavement_marking_311_count_since_2020: mustBeNumber(
      value.pavement_marking_311_count_since_2020,
      "pavement_marking_311_count_since_2020"
    ),
    matched_311_complaints: mustBeComplaintArray(value.matched_311_complaints, "matched_311_complaints"),
    image_url: mustBeString(value.image_url, "image_url"),
    thumbnail_url: mustBeString(value.thumbnail_url, "thumbnail_url"),
    google_maps_url: mustBeString(value.google_maps_url, "google_maps_url"),
    model_score: mustBeNumber(value.model_score, "model_score"),
    heuristic_score: mustBeNumber(value.heuristic_score, "heuristic_score"),
    neighborhood: mustBeString(value.neighborhood, "neighborhood"),
    neighborhood_id: mustBeString(value.neighborhood_id, "neighborhood_id"),
    borough: typeof value.borough === "string" ? value.borough : "Unknown",
    priority_reason: mustBeString(value.priority_reason, "priority_reason"),
    pedestrian_crash_count: mustBeNumber(value.pedestrian_crash_count, "pedestrian_crash_count"),
    top_features: mustBeFeatureArray(value.top_features)
  };
}

function mustBeString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`${field} must be a string.`);
  }

  return value;
}

function mustBeNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`${field} must be a number.`);
  }

  return value;
}

function optionalNumber(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value !== "number" || Number.isNaN(value)) {
    return undefined;
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function mustBeBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${field} must be a boolean.`);
  }

  return value;
}

function mustBeStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must be a string array.`);
  }

  return value;
}

function mustBeYear(value: unknown): 2024 {
  if (value !== 2024) {
    throw new Error("year must be 2024.");
  }

  return 2024;
}

function mustBeFeatureArray(value: unknown): ModelFeatureContribution[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error("top_features must be an array.");
  }
  return value.map((entry, index) => {
    if (!entry || typeof entry !== "object") {
      throw new Error(`top_features[${index}] must be an object.`);
    }
    const feature = entry as Record<string, unknown>;
    return {
      feature: typeof feature.feature === "string" ? feature.feature : "",
      label: typeof feature.label === "string" ? feature.label : String(feature.feature || ""),
      contribution: typeof feature.contribution === "number" ? feature.contribution : 0,
      direction: typeof feature.direction === "string" ? feature.direction : ""
    };
  });
}

function mustBeComplaintArray(value: unknown, field: string): Matched311Complaint[] {
  if (!Array.isArray(value)) {
    throw new Error(`${field} must be an array.`);
  }

  return value.map((entry, index) => {
    if (!entry || typeof entry !== "object") {
      throw new Error(`${field}[${index}] must be an object.`);
    }
    const complaint = entry as Record<string, unknown>;
    return {
      unique_key: mustBeString(complaint.unique_key, `${field}[${index}].unique_key`),
      created_date: mustBeString(complaint.created_date, `${field}[${index}].created_date`),
      descriptor: mustBeString(complaint.descriptor, `${field}[${index}].descriptor`),
      incident_address: mustBeString(complaint.incident_address, `${field}[${index}].incident_address`),
      url: mustBeString(complaint.url, `${field}[${index}].url`)
    };
  });
}
