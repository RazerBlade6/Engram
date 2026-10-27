import { Suspense } from "react";

import { AdminOnly } from "@/components/admin-only";

import { Inspector } from "./inspector";

export default function InspectorPage() {
  // The material id and page number come from the URL, known only at request time.
  return (
    <Suspense>
      <AdminOnly>
        <Inspector />
      </AdminOnly>
    </Suspense>
  );
}
