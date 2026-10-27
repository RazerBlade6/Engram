import { describe, expect, it } from "vitest";

import { MAX_UPLOAD_MB, uploadProblem } from "./uploads";

describe("uploadProblem", () => {
  it("accepts PDF and PowerPoint files", () => {
    expect(uploadProblem({ name: "Week 3.pdf", size: 1000 })).toBeNull();
    expect(uploadProblem({ name: "Lecture.PPTX", size: 1000 })).toBeNull();
  });

  it("explains what to do with an older PowerPoint file", () => {
    expect(uploadProblem({ name: "old.ppt", size: 1000 })).toMatch(/save it as \.pptx/);
  });

  it("refuses other files and files that are too large", () => {
    expect(uploadProblem({ name: "notes.docx", size: 1000 })).toMatch(/PDF and PowerPoint/);
    expect(uploadProblem({ name: "big.pdf", size: (MAX_UPLOAD_MB + 1) * 1024 * 1024 })).toMatch(/over/);
  });
});
