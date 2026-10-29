import type { ReactNode } from "react";

/**
 * A card that turns over to show its back: the one generous animation in Engram. The faces
 * share a grid cell, so the card is as tall as its taller face; the hidden face is inert, so
 * it can't be focused or read out. With reduced motion, the faces swap in place.
 */
export function FlipCard({ flipped, front, back }: { flipped: boolean; front: ReactNode; back: ReactNode }) {
  return (
    <div className="flip" data-flipped={flipped || undefined}>
      <div className="flip-inner">
        <div className="flip-face flip-front" inert={flipped}>
          {front}
        </div>
        <div className="flip-face flip-back" inert={!flipped}>
          {back}
        </div>
      </div>
    </div>
  );
}
