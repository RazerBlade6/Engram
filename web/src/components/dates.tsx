import { KIND_LABEL, chaptersLabel, dayLabel, untilLabel, type CourseDate } from "@/lib/calendar";

/** One upcoming date: what, which course, and when, with the course's color beside it. */
export function DateRow({ date, color, today }: { date: CourseDate; color: string | undefined; today: string }) {
  return (
    <span className="flex items-stretch gap-3">
      <span aria-hidden className="w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <span className="min-w-0">
        <span className="block text-lg font-semibold">{date.title}</span>
        <span className="block text-muted">
          {[date.course, KIND_LABEL[date.kind], chaptersLabel(date.chapters)].filter(Boolean).join(" · ")}
        </span>
        <span className="block">
          {dayLabel(date.on, today)}, {untilLabel(date.on, today)}
        </span>
      </span>
    </span>
  );
}
