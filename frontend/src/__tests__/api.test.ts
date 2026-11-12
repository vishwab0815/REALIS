import { afterEach, describe, expect, it } from "vitest";
import { asset, localize, setAccessCode } from "../api";
import type { CasePayload } from "../types";

afterEach(() => setAccessCode(""));

describe("asset", () => {
  it("adds the access code to evidence files only", () => {
    setAccessCode("s3c ret");
    expect(asset("/cases/C/evidence/x.jpg")).toBe("/cases/C/evidence/x.jpg?key=s3c%20ret");
    expect(asset("/api/health")).toBe("/api/health");
    expect(asset(null)).toBeNull();
  });

  it("leaves URLs untouched when no code is set", () => {
    expect(asset("/cases/C/x.png")).toBe("/cases/C/x.png");
  });

  it("localizes every URL in a result", () => {
    setAccessCode("k");
    const payload = { report: {} as CasePayload["report"], urls: {
      html: "/cases/C/reports/a.html", json: "/cases/C/reports/a.json", evidence: null,
      overview: { "Evidence timeline": "/cases/C/o.png" }, artifacts: { enf: { "ENF track": "/cases/C/e.png" } },
    } } as CasePayload;
    const u = localize(payload).urls;
    expect([u.html, u.overview["Evidence timeline"], u.artifacts.enf["ENF track"]].every((x) => x.endsWith("?key=k"))).toBe(true);
    expect(u.evidence).toBeNull();
  });
});
