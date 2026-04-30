export type ReasonTag =
  | "low contrast"
  | "broken stripes"
  | "partial paint loss"
  | "school zone"
  | `311 x${number} since 2020`;

export interface Matched311Complaint {
  unique_key: string;
  created_date: string;
  descriptor: string;
  incident_address: string;
  url: string;
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
}

export interface CrosswalkMeta {
  build_timestamp: string;
  source_versions: {
    imagery: string;
    lion: string;
    service_requests_311: string;
    school_zones: string;
  };
  pilot_boundary: string;
  total_records: number;
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

  return {
    build_timestamp: mustBeString(value.build_timestamp, "build_timestamp"),
    source_versions: {
      imagery: mustBeString((value.source_versions as Record<string, unknown>)?.imagery, "source_versions.imagery"),
      lion: mustBeString((value.source_versions as Record<string, unknown>)?.lion, "source_versions.lion"),
      service_requests_311: mustBeString(
        (value.source_versions as Record<string, unknown>)?.service_requests_311,
        "source_versions.service_requests_311"
      ),
      school_zones: mustBeString(
        (value.source_versions as Record<string, unknown>)?.school_zones,
        "source_versions.school_zones"
      )
    },
    pilot_boundary: mustBeString(value.pilot_boundary, "pilot_boundary"),
    total_records: mustBeNumber(value.total_records, "total_records")
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
    google_maps_url: mustBeString(value.google_maps_url, "google_maps_url")
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
