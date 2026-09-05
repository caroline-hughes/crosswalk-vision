"use client";

import { useEffect, useRef } from "react";
import type { CrosswalkRecord } from "@crosswalks/contracts";
import { scoreColor, scoreMarkerSize } from "../lib/filters";
import { ORTHO_CAPTION, ORTHO_SCORE_NOTE } from "../lib/imagery";
import { orthoSrc } from "./ortho-frame";
import "leaflet/dist/leaflet.css";

const HOVER_OPEN_MS = 240;
const HOVER_CLOSE_MS = 200;

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
    return `<div class="ortho-block is-empty" aria-hidden="true"><div class="ortho-frame is-empty"><span class="ortho-mark"></span><span>Imagery unavailable</span></div></div>`;
  }
  return `<figure class="ortho-block"><div class="ortho-frame"><img src="${escapeHtml(src)}" alt="${escapeHtml(`${record.intersection_label} ${ORTHO_CAPTION}`)}" onerror="this.onerror=null;this.hidden=true;this.parentElement.classList.add('is-empty');var fallback=this.nextElementSibling;if(fallback){fallback.hidden=false;}" /><div class="ortho-fallback" hidden><span class="ortho-mark"></span><span>Imagery unavailable</span></div></div><figcaption class="ortho-caption"><span>${escapeHtml(ORTHO_CAPTION)}</span><span class="ortho-caption-note">${escapeHtml(ORTHO_SCORE_NOTE)}</span></figcaption></figure>`;
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
  pinnedId,
  scoreMin,
  scoreMax,
  onHover,
  onSelect
}: {
  records: CrosswalkRecord[];
  pinnedId: string | null;
  scoreMin: number;
  scoreMax: number;
  onHover: (record: CrosswalkRecord | null) => void;
  onSelect: (record: CrosswalkRecord | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const markersRef = useRef<Map<string, MarkerEntry>>(new Map());
  const stickyIdRef = useRef<string | null>(null);
  const hoverIdRef = useRef<string | null>(null);
  const hoverOpenTimer = useRef<number | null>(null);
  const hoverCloseTimer = useRef<number | null>(null);
  const overPopupRef = useRef(false);
  const hoverRef = useRef(onHover);
  const selectRef = useRef(onSelect);
  hoverRef.current = onHover;
  selectRef.current = onSelect;

  const clearTimer = (timer: { current: number | null }) => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };

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
        maxZoom: 18,
        closePopupOnClick: false
      }).setView([40.7128, -74.006], 11);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19
      }).addTo(map);

      map.zoomControl.setPosition("bottomright");
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;

      map.on("click", () => {
        if (overPopupRef.current) {
          return;
        }
        stickyIdRef.current = null;
        hoverIdRef.current = null;
        map.closePopup();
        hoverRef.current(null);
        selectRef.current(null);
      });

      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key !== "Escape") {
          return;
        }
        stickyIdRef.current = null;
        hoverIdRef.current = null;
        map.closePopup();
        hoverRef.current(null);
        selectRef.current(null);
      };
      window.addEventListener("keydown", onKeyDown);
      (map as unknown as { __onEsc?: (event: KeyboardEvent) => void }).__onEsc = onKeyDown;

      window.setTimeout(() => map.invalidateSize(), 80);
    }

    setup();

    return () => {
      cancelled = true;
      const map = mapRef.current;
      const onEsc = map ? (map as unknown as { __onEsc?: (event: KeyboardEvent) => void }).__onEsc : undefined;
      if (onEsc) {
        window.removeEventListener("keydown", onEsc);
      }
      map?.remove();
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
      clearTimer(hoverOpenTimer);
      clearTimer(hoverCloseTimer);
      overPopupRef.current = false;

      const closeExclusive = (keepId?: string) => {
        markersRef.current.forEach((entry) => {
          if (entry.record.id !== keepId && entry.marker.isPopupOpen()) {
            entry.marker.closePopup();
          }
        });
      };

      const bindPopupChrome = (entry: MarkerEntry) => {
        const popup = entry.marker.getPopup();
        const element = popup?.getElement();
        if (!element || element.dataset.xingBound === "1") {
          return;
        }
        element.dataset.xingBound = "1";
        L.DomEvent.disableClickPropagation(element);
        L.DomEvent.disableScrollPropagation(element);
        element.addEventListener("mouseenter", () => {
          overPopupRef.current = true;
          clearTimer(hoverCloseTimer);
        });
        element.addEventListener("mouseleave", () => {
          overPopupRef.current = false;
          if (stickyIdRef.current) {
            return;
          }
          clearTimer(hoverCloseTimer);
          hoverCloseTimer.current = window.setTimeout(() => {
            if (stickyIdRef.current || overPopupRef.current) {
              return;
            }
            entry.marker.closePopup();
            hoverIdRef.current = null;
            hoverRef.current(null);
          }, HOVER_CLOSE_MS);
        });
      };

      records.forEach((record) => {
        const color = scoreColor(record.model_score, scoreMin, scoreMax);
        const size = scoreMarkerSize(record.model_score, scoreMin, scoreMax);
        const icon = L.divIcon({
          className: "xing-icon",
          html: iconHtml(color),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
          popupAnchor: [28, -Math.round(size * 0.35)]
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
          autoPan: true,
          autoClose: false,
          closeOnClick: false,
          closeOnEscapeKey: true,
          offset: L.point(18, -14),
          autoPanPadding: L.point(48, 72)
        });

        marker.on("popupopen", () => {
          marker.getElement()?.classList.add("is-lifted");
          bindPopupChrome({ marker, record });
        });
        marker.on("popupclose", () => {
          marker.getElement()?.classList.remove("is-lifted");
          if (stickyIdRef.current === record.id) {
            stickyIdRef.current = null;
            selectRef.current(null);
          }
          if (hoverIdRef.current === record.id) {
            hoverIdRef.current = null;
            hoverRef.current(null);
          }
        });
        marker.on("mouseover", () => {
          marker.getElement()?.classList.add("is-lifted");
          if (stickyIdRef.current || overPopupRef.current) {
            return;
          }
          if (hoverIdRef.current && hoverIdRef.current !== record.id) {
            return;
          }
          clearTimer(hoverCloseTimer);
          clearTimer(hoverOpenTimer);
          hoverOpenTimer.current = window.setTimeout(() => {
            if (stickyIdRef.current || overPopupRef.current) {
              return;
            }
            closeExclusive(record.id);
            hoverIdRef.current = record.id;
            marker.openPopup();
            hoverRef.current(record);
          }, HOVER_OPEN_MS);
        });
        marker.on("mouseout", () => {
          if (stickyIdRef.current !== record.id && hoverIdRef.current !== record.id) {
            marker.getElement()?.classList.remove("is-lifted");
          }
          clearTimer(hoverOpenTimer);
          if (stickyIdRef.current) {
            return;
          }
          clearTimer(hoverCloseTimer);
          hoverCloseTimer.current = window.setTimeout(() => {
            if (stickyIdRef.current || overPopupRef.current) {
              return;
            }
            marker.closePopup();
            hoverIdRef.current = null;
            hoverRef.current(null);
          }, HOVER_CLOSE_MS);
        });
        marker.on("click", (event: import("leaflet").LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(event);
          clearTimer(hoverOpenTimer);
          clearTimer(hoverCloseTimer);
          stickyIdRef.current = record.id;
          hoverIdRef.current = null;
          closeExclusive(record.id);
          marker.openPopup();
          selectRef.current(record);
        });
        marker.addTo(layer);
        markersRef.current.set(record.id, { marker, record });
      });

      if (records.length > 0) {
        const bounds = L.latLngBounds(records.map((row) => [row.lat, row.lon] as [number, number]));
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
    stickyIdRef.current = pinnedId;
    const entry = pinnedId ? markersRef.current.get(pinnedId) : undefined;
    if (entry && !entry.marker.isPopupOpen()) {
      entry.marker.openPopup();
    }
    if (!pinnedId) {
      return;
    }
    markersRef.current.forEach((other) => {
      if (other.record.id !== pinnedId && other.marker.isPopupOpen()) {
        other.marker.closePopup();
      }
    });
  }, [pinnedId]);

  return <div ref={containerRef} className="priority-map" role="presentation" />;
}
