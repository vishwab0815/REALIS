import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalyzerCard, VerdictCard } from "../components/Results";
import { Timeline } from "../components/Timeline";
import { validateFile } from "../components/UploadPanel";
import type { AnalyzerResult, Health } from "../types";

afterEach(cleanup);

// jsdom has no layout engine.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const health: Health = {
  tool: "t", version: "0", runtime: { device: "cpu" }, ffmpeg: true, models: {},
  supported_types: { image: [".jpg"], audio: [".wav"], video: [".mp4"] },
  limits: { max_upload_mb: 1, max_analysis_seconds: 600 },
};

describe("VerdictCard", () => {
  it("shows the label, both meters, rationale and notes", () => {
    render(<VerdictCard notes={["Quick scan: TruFor skipped."]} verdict={{
      label: "Indications of AI generation", manipulation_probability: 0.91, ai_generation_probability: 0.91,
      editing_probability: 0.48, category: "synthesis", decisive: false, rationale: ["[synthetic_voice] Strong signal"],
    }} />);
    expect(screen.getByText("Indications of AI generation")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "AI generation" }).getAttribute("aria-valuenow")).toBe("91");
    expect(screen.getByRole("meter", { name: "Editing / manipulation" }).getAttribute("aria-valuenow")).toBe("48");
    expect(screen.getByText("[synthetic_voice] Strong signal")).toBeTruthy();
    expect(screen.getByText(/Quick scan/)).toBeTruthy();
  });
});

describe("AnalyzerCard", () => {
  const base: AnalyzerResult = {
    analyzer: "enf", title: "ENF", version: "t", status: "ok", evidence_kind: "manipulation", score: 0.85,
    confidence: 0.55, weight: 1.2, decisive_label: null, elapsed_ms: 3, error: null, artifacts: {}, limitations: [],
    findings: [{ severity: "high", title: "Mains-hum discontinuity", detail: "At 18.0 s" }],
    data: { events: [{ time: 18, kind: "enf", label: "ENF break" }] },
  };

  it("renders findings and seeks when an event chip is clicked", () => {
    const onSeek = vi.fn();
    render(<AnalyzerCard result={base} onSeek={onSeek} />);
    expect(screen.getByText("Mains-hum discontinuity")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /ENF break/ }));
    expect(onSeek).toHaveBeenCalledWith(18);
  });

  it("shows why a skipped analyzer did not run", () => {
    render(<AnalyzerCard result={{ ...base, status: "skipped", error: "no audio track" }} />);
    expect(screen.getByText("no audio track")).toBeTruthy();
  });
});

describe("Timeline", () => {
  it("maps a click to a time and supports arrow keys", () => {
    const onSeek = vi.fn();
    render(<Timeline duration={100} currentTime={10} onSeek={onSeek} events={[{ time: 50, kind: "cut" }]}
                     series={[{ name: "AI frames", points: [[0, 0.1], [100, 0.9]] }]} />);
    const svg = screen.getByRole("slider");
    // Width defaults to 800 px: plot spans x = 78 .. 792 (714 px).
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, right: 800, bottom: 80, width: 800, height: 80, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.click(svg, { clientX: 78 + 357 });
    expect(onSeek).toHaveBeenLastCalledWith(50);
    fireEvent.keyDown(svg, { key: "ArrowRight" });
    expect(onSeek).toHaveBeenLastCalledWith(11);
  });
});

describe("validateFile", () => {
  it("rejects unsupported, oversized and empty files", () => {
    expect(validateFile(new File(["x"], "notes.txt"), health)).toMatch(/not a supported type/);
    expect(validateFile(new File([new Uint8Array(2 * 1024 * 1024)], "big.mp4"), health)).toMatch(/limit is 1 MB/);
    expect(validateFile(new File([], "empty.wav"), health)).toMatch(/empty/);
    expect(validateFile(new File(["x"], "ok.jpg"), health)).toBeNull();
  });
});

describe("validateFile without server limits", () => {
  it("refuses to upload until the server's limits are known", () => {
    expect(validateFile(new File(["x"], "ok.jpg"), null)).toMatch(/connecting/);
  });
});
