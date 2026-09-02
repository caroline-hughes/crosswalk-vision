"use client";

import { useEffect, useRef } from "react";
import type { CrosswalkRecord } from "@crosswalks/contracts";
import { heatClass } from "../lib/filters";
import "leaflet/dist/leaflet.css";

function iconHtml(record: CrosswalkRecord): string {
  const heat = heatClass(record.model_score);
  return `<span class="xing-mark xing-${heat}" title="${record.intersection_label}"><span class="xing-bars"></span></span>`;
}

export function PriorityMap({
  records,
  activeId,
  onHover,
  onSelect
}: {
  records: CrosswalkRecord[];
  activeId: string | null;
  onHover: (record: CrosswalkRecord | null) => void;
  onSelect: (record: CrosswalkRecord) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const markersRef = useRef<Map<string, import("leaflet").Marker>>(new Map());
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
        zoomControl: false,
        attributionControl: true,
        minZoom: 10,
        maxZoom: 18
      }).setView([40.7128, -74.006], 11);

      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
        subdomains: "abcd",
        maxZoom: 19
      }).addTo(map);

      L.control.zoom({ position: "bottomright" }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
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
        const icon = L.divIcon({
          className: "xing-icon",
          html: iconHtml(record),
          iconSize: [22, 22],
          iconAnchor: [11, 11]
        });
        const marker = L.marker([record.lat, record.lon], { icon, keyboard: false });
        marker.on("mouseover", () => hoverRef.current(record));
        marker.on("mouseout", () => hoverRef.current(null));
        marker.on("click", () => selectRef.current(record));
        marker.addTo(layer);
        markersRef.current.set(record.id, marker);
      });

      if (records.length > 0) {
        const bounds = L.latLngBounds(records.map((record) => [record.lat, record.lon] as [number, number]));
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [56, 56], maxZoom: 13 });
        }
      }
    }

    paint();
    return () => {
      cancelled = true;
    };
  }, [records]);

  useEffect(() => {
    markersRef.current.forEach((marker, id) => {
      marker.setZIndexOffset(id === activeId ? 1200 : 0);
    });
  }, [activeId]);

  return <div ref={containerRef} className="priority-map" role="presentation" />;
}
