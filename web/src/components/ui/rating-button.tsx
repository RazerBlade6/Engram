import type { Rating } from "@/lib/review";

import { Kbd } from "./kbd";

/**
 * One of the four self-ratings, each in its own ink. The inks say how soon the card comes
 * back, not whether you failed, so "Forgot" isn't red.
 */
export function RatingButton({
  rating,
  label,
  when,
  onClick,
}: {
  rating: Rating;
  label: string;
  /** When this rating brings the card back, e.g. "in 3 days". */
  when: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        color: `var(--rate-${rating})`,
        background: `var(--rate-${rating}-soft)`,
        borderColor: `var(--rate-${rating}-line)`,
      }}
      className="flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-control border px-1 py-2 transition-[filter,translate] duration-150 ease-quiet hover:brightness-[0.96] active:translate-y-0.5 sm:min-h-18 sm:px-2 sm:py-2.5"
    >
      <span className="flex items-center gap-2 font-semibold sm:text-lg">
        <Kbd>{rating}</Kbd>
        {label}
      </span>
      <small className="text-xs opacity-85 sm:text-sm">{when}</small>
    </button>
  );
}
