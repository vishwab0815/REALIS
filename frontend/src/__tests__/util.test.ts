import { describe, expect, it } from "vitest";
import type { AnalyzerResult, Report } from "../types";
import { formatBytes, formatTime, modalityOf, sortResults, timelineData, verdictTone } from "../util";

function result(analyzer: string, data: AnalyzerResult["data"] = {}, status: AnalyzerResult["status"] = "ok"): AnalyzerResult {
  return {
    analyzer, title: analyzer, version: "t", status, evidence_kind: "manipulation", score: 0.5, confidence: 0.3,
    weight: 1, decisive_label: null, findings: [], artifacts: {}, data, limitations: [], elapsed_ms: 1, error: null,
  };
}

function report(results: AnalyzerResult[]): Report {
  return {
    tool: "t", tool_version: "0", generated_at: "2026-11-10T00:00:00Z", modality: "video",
    evidence: { case_id: "C", original_name: "a.mp4", sha256: "x".repeat(64), size_bytes: 1, ingested_at: "" },
    integrity_verified: true, custody_log_valid: true, results, overview: {}, notes: [],
    verdict: { label: "", manipulation_probability: 0, ai_generation_probability: 0, editing_probability: 0,
               category: "none", decisive: false, rationale: [] },
  };
}

describe("timelineData", () => {
  it("collects series, events and frames from successful analyzers only", () => {
    const r = report([
      result("frame_ai", { series: [{ name: "AI frames", points: [[1, 0.2], [9, 0.9]] }],
                           frames: [{ time: 1, path: "f.jpg", probability: 0.2 }] }),
      result("temporal_edits", { events: [{ time: 4, kind: "cut" }] }),
      result("enf", { events: [{ time: 99, kind: "enf" }] }, "skipped"),
      result("video_metadata", { duration_s: 12.5 }),
    ]);
    const t = timelineData(r);
    expect(t.series.map((s) => s.name)).toEqual(["AI frames"]);
    expect(t.events).toEqual([{ time: 4, kind: "cut" }]);
    expect(t.frames).toHaveLength(1);
    expect(t.duration).toBe(12.5);
  });

  it("falls back to the latest marked time when no duration is declared", () => {
    const t = timelineData(report([result("x", { events: [{ time: 3, end: 7.5, kind: "synthetic" }] })]));
    expect(t.duration).toBe(7.5);
  });

  it("drops empty series", () => {
    const t = timelineData(report([result("x", { series: [{ name: "AI voice", points: [] }] })]));
    expect(t.series).toEqual([]);
  });
});

describe("formatting", () => {
  it("formats times", () => {
    expect(formatTime(75.4)).toBe("1:15");
    expect(formatTime(75.4, true)).toBe("1:15.4");
    expect(formatTime(3725)).toBe("1:02:05");
  });
  it("formats sizes", () => {
    expect(formatBytes(512)).toBe("1 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("verdictTone", () => {
  it("maps probability and category to a tone", () => {
    expect(verdictTone(0.2, "none")).toBe("ok");
    expect(verdictTone(0.5, "manipulation")).toBe("warn");
    expect(verdictTone(0.9, "synthesis")).toBe("ai");
    expect(verdictTone(0.9, "manipulation")).toBe("bad");
  });
});

describe("modalityOf", () => {
  const types = { image: [".jpg"], audio: [".wav"], video: [".mp4"] };
  it("classifies by extension, case-insensitively", () => {
    expect(modalityOf("A.JPG", types)).toBe("image");
    expect(modalityOf("clip.mp4", types)).toBe("video");
    expect(modalityOf("notes.txt", types)).toBeNull();
    expect(modalityOf("noext", types)).toBeNull();
  });
});

describe("sortResults", () => {
  it("puts evidence analyzers first and skipped ones last", () => {
    const sorted = sortResults([result("ela"), result("frame_ai", {}, "skipped"), result("c2pa_provenance"), result("enf")]);
    expect(sorted.map((r) => r.analyzer)).toEqual(["c2pa_provenance", "enf", "ela", "frame_ai"]);
  });
});
