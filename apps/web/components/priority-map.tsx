"use client";

import { useEffect, useRef } from "react";
import type { CrosswalkRecord } from "@crosswalks/contracts";
import { scoreColor, scoreMarkerSize } from "../lib/filters";
import { ORTHO_CAPTION } from "../lib/imagery";
import { orthoSrc } from "./ortho-frame";
import "leaflet/dist/leaflet.css";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function iconHtml(color: string): string {
  return `<span class="xing-pin" style="--pin:${color}"><span class="xing-bars" aria-hidden="true"></span></span>`;
}

function photoHtml(record: CrosswalkRecord): string {
  const src = orthoSrc(record);
  if (!src) {
    return `<div class="ortho-block is-empty" aria-hidden="true"><div class="ortho-frame is-empty"><span class="ortho-mark"></span><span>Ortho unavailable</span></div></div>`;
  }
  return `<figure class="ortho-block"><div class="ortho-frame"><img src="${escapeHtml(src)}" alt="${escapeHtml(`${record.intersection_label} ${ORTHO_CAPTION}`)}" /></div><figcaption class="ortho-caption">${escapeHtml(ORTHO_CAPTION)}</figcaption></figure>`;
}

function popupHtml(record: CrosswalkRecord): string {
  const probability = Math.round(record.model_score * 100);
  const features = record.top_features
    .slice(0, 3)
    .map((feature) => {
      const sign = feature.contribution >= 0 ? "+" : "";
      return `<li><span>${escapeHtml(feature.label)}</span><b class="${feature.contribution >= 0 ? "up" : "down"}">${sign}${feature.contribution.toFixed(2)}</b></li>`;
    })
    .join("");
  const complaints = record.matched_311_complaints
    .slice(0, 3)
    .map((complaint) => {
      const date = new Date(complaint.created_date);
      const label = Number.isNaN(date.getTime()) ? complaint.created_date : date.toLocaleDateString();
      return `<a href="${escapeHtml(complaint.url)}" target="_blank" rel="noreferrer">${escapeHtml(label)} — ${escapeHtml(complaint.descriptor)}</a>`;
    })
    .join("");
  return `
    <article class="hover-card leaflet-hover">
      <span class="tape" aria-hidden="true"></span>
      ${photoHtml(record)}
      <header class="hover-card-head">
        <div>
          <p class="hover-kicker">${escapeHtml(record.borough)} · ${escapeHtml(record.neighborhood || record.neighborhood_id)}</p>
          <h2>${escapeHtml(record.intersection_label)}</h2>
        </div>
        <div class="model-badge" title="Learned P(pedestrian crash nearby)">
          <span>P(crash)</span>
          <strong>${probability}</strong>
        </div>
      </header>
      <p class="hover-why">${escapeHtml(record.priority_reason)}</p>
      <dl class="hover-stats">
        <div><dt>Heuristic</dt><dd>${Math.round(record.heuristic_score)}</dd></div>
        <div><dt>Crashes</dt><dd>${record.pedestrian_crash_count}</dd></div>
        <div><dt>311</dt><dd>${record.pavement_marking_311_count_since_2020}</dd></div>
      </dl>
      ${features ? `<p class="why-label">Why the model flagged this</p><ul class="feature-list">${features}</ul>` : ""}
      <div class="hover-311">
        <p>311 faded markings since 2020: ${record.pavement_marking_311_count_since_2020}. Mixed lane lines and crosswalks.</p>
        ${complaints}
      </div>
      <a class="hover-maps" href="${escapeHtml(record.google_maps_url)}" target="_blank" rel="noreferrer">Open in Google Maps</a>
    </article>
  `;
}

type MarkerEntry = {
  marker: import("leaflet").Marker;
  record: CrosswalkRecord;
};

export function PriorityMap({
  records,
  activeId,
  scoreMin,
  scoreMax,
  onHover,
  onSelect
}: {
  records: CrosswalkRecord[];
  activeId: string | null;
  scoreMin: number;
  scoreMax: number;
  onHover: (record: CrosswalkRecord | null) => void;
  onSelect: (record: CrosswalkRecord) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const markersRef = useRef<Map<string, MarkerEntry>>(new Map());
  const lastPopupId = useRef<string | null>(null);
  const hoverRef = useRef(onHover);
  const selectRef = useRef(onSelect);
  hoverRef.current = onHover;
  selectRef.current = onSelect;

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      const L = await import("leaflet");
      if (cancelled || !containerRef.current || mapRef.current) {
        return;
      }

      const map = L.map(containerRef.current, {
        zoomControl: true,
        attributionControl: true,
        scrollWheelZoom: true,
        doubleClickZoom: true,
        dragging: true,
        minZoom: 10,
        maxZoom: 18
      }).setView([40.7128, -74.006], 11);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19
      }).addTo(map);

      map.zoomControl.setPosition("bottomright");
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;

      const openNearest = (latlng: import("leaflet").LatLng, sticky: boolean) => {
        const origin = map.latLngToContainerPoint(latlng);
        let best: MarkerEntry | undefined;
        let bestD = 28;
        markersRef.current.forEach((entry) => {
          const point = map.latLngToContainerPoint(entry.marker.getLatLng());
          const distance = origin.distanceTo(point);
          if (distance < bestD) {
            bestD = distance;
            best = entry;
          }
        });
        markersRef.current.forEach((entry) => {
          const el = entry.marker.getElement();
          el?.classList.toggle("is-lifted", Boolean(best && entry.record.id === best.record.id));
        });
        if (!best) {
          return;
        }
        if (lastPopupId.current !== best.record.id) {
          lastPopupId.current = best.record.id;
          best.marker.openPopup();
        }
        hoverRef.current(best.record);
        if (sticky) {
          selectRef.current(best.record);
        }
      };

      map.on("mousemove", (event: import("leaflet").LeafletMouseEvent) => {
        openNearest(event.latlng, false);
      });
      map.on("click", (event: import("leaflet").LeafletMouseEvent) => {
        openNearest(event.latlng, true);
      });
      window.setTimeout(() => map.invalidateSize(), 80);
    }

    setup();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
      markersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let tries = 0;

    async function paint() {
      const L = await import("leaflet");
      while (!cancelled && (!mapRef.current || !layerRef.current) && tries < 40) {
        tries += 1;
        await new Promise((resolve) => window.setTimeout(resolve, 50));
      }
      const map = mapRef.current;
      const layer = layerRef.current;
      if (cancelled || !map || !layer) {
        return;
      }

      layer.clearLayers();
      markersRef.current.clear();

      records.forEach((record) => {
        const color = scoreColor(record.model_score, scoreMin, scoreMax);
        const size = scoreMarkerSize(record.model_score, scoreMin, scoreMax);
        const icon = L.divIcon({
          className: "xing-icon",
          html: iconHtml(color),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
          popupAnchor: [0, -Math.round(size * 0.55)]
        });
        const marker = L.marker([record.lat, record.lon], {
          icon,
          keyboard: true,
          riseOnHover: true
        });
        marker.bindPopup(popupHtml(record), {
          className: "xing-popup",
          maxWidth: 360,
          minWidth: 280,
          closeButton: true,
          autoPan: false
        });
        marker.on("mouseover", () => {
          marker.getElement()?.classList.add("is-lifted");
          marker.openPopup();
          hoverRef.current(record);
        });
        marker.on("mouseout", () => {
          marker.getElement()?.classList.remove("is-lifted");
        });
        marker.on("click", () => {
          marker.openPopup();
          selectRef.current(record);
        });
        marker.addTo(layer);
        markersRef.current.set(record.id, { marker, record });
      });

      if (records.length > 0) {
        const bounds = L.latLngBounds(records.map((record) => [record.lat, record.lon] as [number, number]));
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [56, 56], maxZoom: 13 });
        }
        window.setTimeout(() => map.invalidateSize(), 50);
      }
    }

    paint();
    return () => {
      cancelled = true;
    };
  }, [records, scoreMin, scoreMax]);

  useEffect(() => {
    const entry = activeId ? markersRef.current.get(activeId) : undefined;
    if (entry && !entry.marker.isPopupOpen()) {
      entry.marker.openPopup();
    }
  }, [activeId]);

  return <div ref={containerRef} className="priority-map" role="presentation" />;
}
