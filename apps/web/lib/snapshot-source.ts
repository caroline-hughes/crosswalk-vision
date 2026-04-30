import {
  validateCrosswalkMeta,
  validateCrosswalkRecords,
  type CrosswalkMeta,
  type CrosswalkRecord
} from "@crosswalks/contracts";

export interface CrosswalkSnapshot {
  crosswalks: CrosswalkRecord[];
  meta: CrosswalkMeta;
}

export interface CrosswalkSnapshotSource {
  loadSnapshot(): Promise<CrosswalkSnapshot>;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);

  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}`);
  }

  return (await response.json()) as T;
}

export const staticSnapshotSource: CrosswalkSnapshotSource = {
  async loadSnapshot() {
    const [rawCrosswalks, rawMeta] = await Promise.all([
      fetchJson<unknown>("/data/crosswalks.json"),
      fetchJson<unknown>("/data/meta.json")
    ]);

    return {
      crosswalks: validateCrosswalkRecords(rawCrosswalks),
      meta: validateCrosswalkMeta(rawMeta)
    };
  }
};
