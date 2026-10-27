import { Suspense } from "react";

import { ReviewView } from "./review-view";

export default function ReviewPage() {
  // Which session (review or quiz) comes from the URL, known only at request time.
  return (
    <Suspense>
      <ReviewView />
    </Suspense>
  );
}
