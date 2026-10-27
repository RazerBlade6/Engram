import { Suspense } from "react";

import { AskView } from "./ask-view";

export default function AskPage() {
  // The course comes from the URL, known only at request time.
  return (
    <Suspense>
      <AskView />
    </Suspense>
  );
}
