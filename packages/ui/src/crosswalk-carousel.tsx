"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CrosswalkRecord } from "@crosswalks/contracts";
import { CrosswalkCard } from "./crosswalk-card";

export function CrosswalkCarousel({ records }: { records: CrosswalkRecord[] }) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const maxIndex = Math.max(records.length - 1, 0);

  const scrollToIndex = (index: number) => {
    const track = trackRef.current;
    if (!track) {
      return;
    }

    const safeIndex = Math.max(0, Math.min(index, maxIndex));
    const card = track.children.item(safeIndex) as HTMLElement | null;
    if (!card) {
      return;
    }

    track.scrollTo({
      left: card.offsetLeft,
      behavior: "smooth"
    });
    setActiveIndex(safeIndex);
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") {
        scrollToIndex(activeIndex + 1);
      }

      if (event.key === "ArrowLeft") {
        scrollToIndex(activeIndex - 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, maxIndex]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) {
      return;
    }

    const handleScroll = () => {
      const cards = Array.from(track.children) as HTMLElement[];
      const nextIndex = cards.findIndex((card) => {
        const left = Math.abs(card.offsetLeft - track.scrollLeft);
        return left < card.clientWidth * 0.35;
      });

      if (nextIndex >= 0) {
        setActiveIndex(nextIndex);
      }
    };

    track.addEventListener("scroll", handleScroll, { passive: true });
    return () => track.removeEventListener("scroll", handleScroll);
  }, []);

  const emptyState = useMemo(() => records.length === 0, [records.length]);

  if (emptyState) {
    return <div className="status-panel">No crosswalks matched this filter.</div>;
  }

  return (
    <section className="carousel-shell" aria-label="Inspection priority list">
      <button
        type="button"
        className="nav-button"
        onClick={() => scrollToIndex(activeIndex - 1)}
        disabled={activeIndex <= 0}
        aria-label="Previous crosswalk"
      >
        ←
      </button>

      <div className="track" ref={trackRef}>
        {records.map((record) => (
          <CrosswalkCard key={record.id} record={record} />
        ))}
      </div>

      <button
        type="button"
        className="nav-button"
        onClick={() => scrollToIndex(activeIndex + 1)}
        disabled={activeIndex >= maxIndex}
        aria-label="Next crosswalk"
      >
        →
      </button>
    </section>
  );
}
