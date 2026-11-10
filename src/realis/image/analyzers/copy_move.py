"""Copy-move (clone) detection via SIFT self-matching and geometric verification."""

from __future__ import annotations

import cv2
import numpy as np

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, Finding, Severity

MAX_DIM = 1600
G2NN_RATIO = 0.5
MIN_INLIERS = 10
MAX_CLUSTERS = 3


def _self_matches(des: np.ndarray) -> list[tuple[int, int]]:
    """Generalised 2-NN test: keep every neighbour that is much closer than the next."""
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    knn = matcher.knnMatch(des, des, k=min(6, len(des)))
    pairs = set()
    for ms in knn:
        for k in range(1, len(ms) - 1):  # ms[0] is the keypoint itself
            if ms[k].distance >= G2NN_RATIO * ms[k + 1].distance:
                break
            i, j = ms[k].queryIdx, ms[k].trainIdx
            pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


@register
class CopyMoveAnalyzer(Analyzer):
    name = "copy_move"
    title = "Copy-move (clone) detection"
    modalities = ("image",)
    weight = 1.2
    description = "Cloned regions within the image (SIFT g2NN + RANSAC similarity transform)"

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        gray = ctx.gray
        scale = min(1.0, MAX_DIM / max(gray.shape))
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
        small = small.astype(np.uint8)
        min_dist = max(20.0, 0.03 * max(small.shape))

        sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.02)
        kps, des = sift.detectAndCompute(small, None)
        if des is None or len(kps) < 30:
            return self.result(score=0.5, confidence=0.0, findings=[Finding(
                severity=Severity.INFO, title="Too few keypoints for copy-move analysis",
                detail=f"{0 if des is None else len(kps)} keypoints (flat or tiny image).")])

        pts = np.array([kp.pt for kp in kps], dtype=np.float32)
        pairs = [(i, j) for i, j in _self_matches(des) if np.linalg.norm(pts[i] - pts[j]) > min_dist]
        src = np.array([pts[i] for i, _ in pairs], dtype=np.float32).reshape(-1, 2)
        dst = np.array([pts[j] for _, j in pairs], dtype=np.float32).reshape(-1, 2)
        # Orient every pair the same way so one transform can explain a whole clone.
        flip = (dst[:, 0] - src[:, 0] < -1) | ((np.abs(dst[:, 0] - src[:, 0]) <= 1) & (dst[:, 1] < src[:, 1]))
        src[flip], dst[flip] = dst[flip].copy(), src[flip].copy()

        clusters = []
        remaining = np.ones(len(src), dtype=bool)
        for _ in range(MAX_CLUSTERS):
            idx = np.nonzero(remaining)[0]
            if len(idx) < MIN_INLIERS:
                break
            m, inl = cv2.estimateAffinePartial2D(src[idx], dst[idx], method=cv2.RANSAC,
                                                 ransacReprojThreshold=4.0, maxIters=4000)
            if m is None or inl is None or int(inl.sum()) < MIN_INLIERS:
                break
            members = idx[inl.ravel().astype(bool)]
            remaining[members] = False
            spread = np.ptp(src[members], axis=0)
            shift = float(np.hypot(m[0, 2], m[1, 2]))
            if max(spread) < 12 or shift < min_dist:
                continue  # degenerate: a point blob or a near-identity transform
            clusters.append({
                "inliers": int(len(members)),
                "rotation_deg": round(float(np.degrees(np.arctan2(m[1, 0], m[0, 0]))), 1),
                "scale": round(float(np.hypot(m[0, 0], m[1, 0])), 3),
                "src_bbox": [round(float(v) / scale) for v in (*src[members].min(0), *spread)],
                "dst_bbox": [round(float(v) / scale) for v in (*dst[members].min(0), *np.ptp(dst[members], axis=0))],
                "src": (src[members] / scale).tolist(),
                "dst": (dst[members] / scale).tolist(),
            })

        findings, artifacts = [], {}
        if clusters:
            best = max(c["inliers"] for c in clusters)
            score, conf = (0.88, 0.6) if best >= 20 else (0.72, 0.45)
            for c in clusters:
                findings.append(Finding(
                    severity=Severity.HIGH if c["inliers"] >= 20 else Severity.MEDIUM,
                    title="Duplicated region detected",
                    detail=f"{c['inliers']} matching keypoints; source x,y,w,h={c['src_bbox']} -> "
                           f"copy {c['dst_bbox']}; rotation {c['rotation_deg']} deg, scale {c['scale']}.",
                ))
            artifacts["Copy-move matches"] = ctx.save_image("copy_move", self._draw(ctx.rgb, clusters))
        else:
            score, conf = 0.4, 0.25
            findings.append(Finding(severity=Severity.INFO, title="No cloned regions found",
                                    detail=f"{len(kps)} keypoints, {len(pairs)} candidate pairs."))

        return self.result(
            score=score, confidence=conf, findings=findings, artifacts=artifacts,
            data={"keypoints": len(kps), "candidate_pairs": len(pairs),
                  "clusters": [{k: v for k, v in c.items() if k not in ("src", "dst")} for c in clusters]},
            limitations=[
                "Repetitive real-world patterns (tiles, windows, crowds) can cause false matches.",
                "Clones of flat, textureless areas have no keypoints and are not detected.",
            ],
        )

    @staticmethod
    def _draw(rgb: np.ndarray, clusters: list[dict]) -> np.ndarray:
        vis = rgb.copy()
        thick = max(1, round(max(rgb.shape[:2]) / 600))
        colors = [(0, 255, 0), (255, 200, 0), (0, 200, 255)]
        for c, color in zip(clusters, colors):
            for (x1, y1), (x2, y2) in zip(c["src"], c["dst"]):
                p1, p2 = (round(x1), round(y1)), (round(x2), round(y2))
                cv2.line(vis, p1, p2, color, thick)
                cv2.circle(vis, p1, 3 * thick, (255, 0, 0), -1)
                cv2.circle(vis, p2, 3 * thick, (0, 0, 255), -1)
        return vis
