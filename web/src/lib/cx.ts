/** Joins class names, skipping the falsy ones: `cx("a", busy && "b")`. */
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
