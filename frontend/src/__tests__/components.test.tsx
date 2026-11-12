import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Header } from "../components/Chrome";
import { layerInfo } from "../components/MediaStage";
import { Modal } from "../components/Modal";
import { AnalyzerDetails, CheckList, KeyFindings, VerdictSummary, keyFindings } from "../components/Results";
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
  tool: "realis", version: "0.4.0", runtime: { device: "cuda", gpu: "Test GPU" }, ffmpeg: true,
  models: { synthetic_voice: { installed: true, loaded: true, enabled: true } },
  supported_types: { image: [".jpg"], audio: [".wav"], video: [".mp4"] },
  limits: { max_upload_mb: 1, max_analysis_seconds: 600 },
};

const enf: AnalyzerResult = {
  analyzer: "enf", title: "ENF", version: "t", status: "ok", evidence_kind: "manipulation", score: 0.85,
  confidence: 0.55, weight: 1.2, decisive_label: null, elapsed_ms: 3, error: null, artifacts: {}, limitations: ["Needs hum."],
  findings: [{ severity: "high", title: "Mains-hum discontinuity", detail: "At 18.0 s" }],
  data: { events: [{ time: 18, kind: "enf", label: "ENF break" }] },
};
const clean: AnalyzerResult = {
  ...enf, analyzer: "copy_move", title: "Copy-move", score: 0.4, confidence: 0.25, data: {},
  findings: [{ severity: "info", title: "No cloned regions found", detail: "" }],
};
const skipped: AnalyzerResult = { ...enf, analyzer: "synthetic_voice", title: "AI voice", status: "skipped", error: "no audio track" };

describe("VerdictSummary", () => {
  it("shows the label, risk ring and both meters, and asks for the explanation on demand", () => {
    const onExplain = vi.fn();
    render(<VerdictSummary onExplain={onExplain} verdict={{
      label: "Indications of AI generation", manipulation_probability: 0.91, ai_generation_probability: 0.91,
      editing_probability: 0.48, category: "synthesis", decisive: false, rationale: ["[synthetic_voice] Strong signal"],
    }} />);
    expect(screen.getByText("Indications of AI generation")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Risk 91%" })).toBeTruthy();
    expect(screen.getByRole("meter", { name: "AI generation" }).getAttribute("aria-valuenow")).toBe("91");
    // The rationale is not on the summary; it lives behind "Why this verdict?".
    expect(screen.queryByText("[synthetic_voice] Strong signal")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Why this verdict/ }));
    expect(onExplain).toHaveBeenCalled();
  });

  it("shows case notes quietly inside the verdict card", () => {
    render(<VerdictSummary onExplain={vi.fn()} notes={["Quick scan: deep-scan analyzers (TruFor) were skipped."]} verdict={{
      label: "No significant evidence", manipulation_probability: 0.3, ai_generation_probability: 0.2,
      editing_probability: 0.3, category: "none", decisive: false, rationale: [],
    }} />);
    const note = screen.getByText(/TruFor\) were skipped/);
    expect(note.closest(".verdict")).toBeTruthy();
  });
});

describe("layerInfo", () => {
  it("gives every image layer a short button name and an explanation", () => {
    expect(layerInfo("ELA anomaly map (texture-normalised)")).toMatchObject({ short: "ELA anomalies" });
    expect(layerInfo("Noise inconsistency map").hint).toMatch(/does not match/);
    expect(layerInfo("TruFor localization map").short).toBe("TruFor map");
  });

  it("shortens labels it does not know by dropping brackets and a trailing 'map'", () => {
    expect(layerInfo("Spectral residue map (log scale)")).toEqual({ short: "Spectral residue", hint: "" });
    expect(layerInfo("Frequency spectrum").short).toBe("Frequency spectrum");
  });
});

describe("KeyFindings and CheckList", () => {
  it("lists only significant findings, most severe first", () => {
    expect(keyFindings([clean, enf]).map((k) => k.finding.title)).toEqual(["Mains-hum discontinuity"]);
    const onOpen = vi.fn();
    render(<KeyFindings results={[clean, enf]} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /Mains-hum discontinuity/ }));
    expect(onOpen).toHaveBeenCalledWith("enf");
  });

  it("drops the empty findings card and says so in the check list instead", () => {
    const { container } = render(<KeyFindings results={[clean]} onOpen={vi.fn()} />);
    expect(container.firstChild).toBeNull();
    render(<CheckList results={[clean]} onOpen={vi.fn()} />);
    expect(screen.getByText(/No significant findings across 1 checks/)).toBeTruthy();
  });

  it("does not claim a clear result when there are significant findings", () => {
    render(<CheckList results={[clean, enf]} onOpen={vi.fn()} />);
    expect(screen.queryByText(/No significant findings/)).toBeNull();
  });

  it("shows one line per check and opens details on click", () => {
    const onOpen = vi.fn();
    render(<CheckList results={[enf, clean, skipped]} onOpen={onOpen} />);
    expect(screen.getByText("Skipped · no audio track")).toBeTruthy();
    expect(screen.queryByText("At 18.0 s")).toBeNull(); // details stay in the modal
    fireEvent.click(screen.getByRole("button", { name: "Copy-move: details" }));
    expect(onOpen).toHaveBeenCalledWith("copy_move");
  });
});

describe("AnalyzerDetails", () => {
  it("shows full findings and limitations, and jump-to-moment chips seek", () => {
    const onSeek = vi.fn();
    render(<AnalyzerDetails result={enf} caseId="C" figures={{}} onSeek={onSeek} onFigure={vi.fn()} />);
    expect(screen.getByText("At 18.0 s")).toBeTruthy();
    expect(screen.getByText("Needs hum.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /ENF break/ }));
    expect(onSeek).toHaveBeenCalledWith(18);
  });

  it("explains why a skipped check did not run", () => {
    render(<AnalyzerDetails result={skipped} caseId="C" figures={{}} onFigure={vi.fn()} />);
    expect(screen.getByText(/did not run: no audio track/)).toBeTruthy();
  });
});

describe("Modal", () => {
  it("closes on Escape, on the close button and on a backdrop click", () => {
    const onClose = vi.fn();
    render(<Modal title="Details" onClose={onClose}><p>Body</p></Modal>);
    expect(screen.getByRole("dialog", { name: "Details" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.mouseDown(document.querySelector(".modal-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});

describe("Header", () => {
  it("summarises system status in one pill and shows details in a modal", () => {
    render(<Header health={health} error={null} />);
    fireEvent.click(screen.getByRole("button", { name: "System status: Ready · GPU" }));
    expect(screen.getByRole("dialog", { name: "System status" })).toBeTruthy();
    expect(screen.getByText("GPU · Test GPU")).toBeTruthy();
  });

  it("reports an unreachable server", () => {
    render(<Header health={null} error="fetch failed" />);
    expect(screen.getByRole("button", { name: "System status: Server offline" })).toBeTruthy();
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

  it("refuses to upload until the server's limits are known", () => {
    expect(validateFile(new File(["x"], "ok.jpg"), null)).toMatch(/connecting/);
  });
});
