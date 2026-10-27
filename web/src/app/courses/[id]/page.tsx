import { Suspense } from "react";

import { CourseView } from "./course-view";

export default function CoursePage() {
  // The course id comes from the URL, known only at request time.
  return (
    <Suspense>
      <CourseView />
    </Suspense>
  );
}
