from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover
    RapidOCR = None


@dataclass
class DetectedRegion:
    index: int
    label: str
    bbox: Tuple[int, int, int, int]  # (x, y, w, h) in window-relative pixels
    kind: str = "panel"  # "panel" | "element" | "subzone"
    confidence: float = 1.0
    description: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Tuple[int, int]:
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)


class VisionGrounder:
    """Dynamic OpenCV panel segmenter + scoped OCR/contour element detector."""

    def __init__(self) -> None:
        self._ocr: Optional[Any] = None
        self._ocr_initialized = False

    def _get_ocr(self) -> Optional[Any]:
        if not self._ocr_initialized:
            self._ocr_initialized = True
            if RapidOCR is not None:
                try:
                    self._ocr = RapidOCR()
                except Exception:
                    self._ocr = None
        return self._ocr

    @staticmethod
    def capture_window_region(
        left: int,
        top: int,
        width: int,
        height: int,
        exclude_rect: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[np.ndarray]:
        """Capture a screen region as a BGR numpy array and optionally mask an overlay rect."""
        if width <= 20 or height <= 20 or mss is None:
            return None

        with mss.mss() as sct:
            monitor = {
                "left": int(left),
                "top": int(top),
                "width": int(width),
                "height": int(height),
            }
            raw = np.array(sct.grab(monitor))

        if raw.size == 0:
            return None

        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

        if exclude_rect is not None:
            ex_x, ex_y, ex_w, ex_h = exclude_rect
            rel_x1 = max(0, ex_x - left)
            rel_y1 = max(0, ex_y - top)
            rel_x2 = min(width, ex_x + ex_w - left)
            rel_y2 = min(height, ex_y + ex_h - top)
            if rel_x2 > rel_x1 and rel_y2 > rel_y1:
                cv2.rectangle(bgr, (rel_x1, rel_y1), (rel_x2, rel_y2), (30, 30, 30), -1)

        return bgr

    @staticmethod
    def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = float((x2 - x1) * (y2 - y1))
        union = float(aw * ah + bw * bh - inter)
        return inter / union if union > 0 else 0.0

    @classmethod
    def _merge_boxes(
        cls, boxes: List[Tuple[int, int, int, int]], iou_threshold: float = 0.45
    ) -> List[Tuple[int, int, int, int]]:
        merged: List[Tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda r: (r[1], r[0])):
            placed = False
            for idx, existing in enumerate(merged):
                if cls._iou(box, existing) >= iou_threshold:
                    x1 = min(existing[0], box[0])
                    y1 = min(existing[1], box[1])
                    x2 = max(existing[0] + existing[2], box[0] + box[2])
                    y2 = max(existing[1] + existing[3], box[1] + box[3])
                    merged[idx] = (x1, y1, x2 - x1, y2 - y1)
                    placed = True
                    break
            if not placed:
                merged.append(box)
        return merged

    def detect_panels(self, frame_bgr: np.ndarray, max_panels: int = 8) -> List[DetectedRegion]:
        """Detect major UI containers/panels dynamically via divider lines and distinct regions."""
        h, w = frame_bgr.shape[:2]
        if h < 50 or w < 50:
            return []

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 25, 95)

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 6), 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, h // 6)))

        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)

        # Find prominent horizontal and vertical split coordinates
        h_proj = np.sum(h_lines > 0, axis=1)
        v_proj = np.sum(v_lines > 0, axis=0)

        y_splits = [0]
        for y in range(int(h * 0.05), int(h * 0.92)):
            if h_proj[y] >= int(w * 0.25) and all(abs(y - prev) > int(h * 0.08) for prev in y_splits):
                y_splits.append(y)
        y_splits.append(h)

        x_splits = [0]
        for x in range(int(w * 0.03), int(w * 0.97)):
            if v_proj[x] >= int(h * 0.20) and all(abs(x - prev) > int(w * 0.05) for prev in x_splits):
                x_splits.append(x)
        x_splits.append(w)

        grid_boxes: List[Tuple[int, int, int, int]] = []
        for r in range(len(y_splits) - 1):
            y1, y2 = y_splits[r], y_splits[r + 1]
            if y2 - y1 < 32:
                continue
            for c in range(len(x_splits) - 1):
                x1, x2 = x_splits[c], x_splits[c + 1]
                if x2 - x1 < 36:
                    continue
                area = (x2 - x1) * (y2 - y1)
                if area >= max(2400, int(w * h * 0.012)):
                    grid_boxes.append((x1, y1, x2 - x1, y2 - y1))

        # Fallback to contour detection if structural grid lines are minimal
        if len(grid_boxes) < 2:
            close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, close_k, iterations=1)
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                area = cw * ch
                if max(2000, int(w * h * 0.01)) <= area <= int(w * h * 0.85) and cw >= 35 and ch >= 30:
                    grid_boxes.append((x, y, cw, ch))

        panels = self._merge_boxes(grid_boxes, iou_threshold=0.50)
        panels = sorted(panels, key=lambda r: r[2] * r[3], reverse=True)[:max_panels]
        panels = sorted(panels, key=lambda r: (r[1] // max(1, h // 4), r[0]))

        return [
            DetectedRegion(
                index=i + 1,
                label=f"Sector {i + 1}",
                bbox=box,
                kind="panel",
            )
            for i, box in enumerate(panels)
        ]

    def detect_sector_elements(
        self,
        frame_bgr: np.ndarray,
        sector_bbox: Tuple[int, int, int, int],
        knowledge_map: Optional[Dict[str, str]] = None,
        max_elements: int = 18,
    ) -> List[DetectedRegion]:
        """Detect interactive elements and OCR text labels strictly inside sector_bbox."""
        sx, sy, sw, sh = sector_bbox
        fh, fw = frame_bgr.shape[:2]
        x1 = max(0, sx)
        y1 = max(0, sy)
        x2 = min(fw, sx + sw)
        y2 = min(fh, sy + sh)
        if x2 <= x1 or y2 <= y1:
            return []

        crop = frame_bgr[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        candidates: List[Tuple[str, Tuple[int, int, int, int], float, str]] = []

        ocr = self._get_ocr()
        if ocr is not None:
            try:
                result, _ = ocr(crop)
                if result:
                    for item in result:
                        quad, text, score = item[0], str(item[1]).strip(), float(item[2])
                        if not text or score < 0.45:
                            continue
                        xs = [int(pt[0]) for pt in quad]
                        ys = [int(pt[1]) for pt in quad]
                        bx = x1 + max(0, min(xs))
                        by = y1 + max(0, min(ys))
                        bw = max(12, max(xs) - min(xs))
                        bh = max(10, max(ys) - min(ys))
                        desc = self._lookup_knowledge(text, knowledge_map)
                        candidates.append((text, (bx, by, bw, bh), score, desc))
            except Exception:
                pass

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 35, 120)
        dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, dilate_k, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            if 14 <= rw <= max(28, cw // 2) and 14 <= rh <= max(28, ch // 2):
                box = (x1 + rx, y1 + ry, rw, rh)
                if not any(self._iou(box, c[1]) > 0.40 for c in candidates):
                    candidates.append(("Control", box, 0.7, ""))

        candidates.sort(key=lambda c: (c[1][1] // 24, c[1][0]))
        trimmed = candidates[:max_elements]

        return [
            DetectedRegion(
                index=idx + 1,
                label=label,
                bbox=box,
                kind="element",
                confidence=conf,
                description=desc,
            )
            for idx, (label, box, conf, desc) in enumerate(trimmed)
        ]

    @staticmethod
    def subdivide_box(
        bbox: Tuple[int, int, int, int], rows: int = 2, cols: int = 2
    ) -> List[DetectedRegion]:
        """Split a dense target box into a clean sub-zone grid for fine clicks."""
        x, y, w, h = bbox
        cell_w = max(1, w // cols)
        cell_h = max(1, h // rows)
        out: List[DetectedRegion] = []
        idx = 1
        for r in range(rows):
            for c in range(cols):
                cx = x + c * cell_w
                cy = y + r * cell_h
                cw = (w - c * cell_w) if c == cols - 1 else cell_w
                ch = (h - r * cell_h) if r == rows - 1 else cell_h
                out.append(
                    DetectedRegion(
                        index=idx,
                        label=f"Zone {idx}",
                        bbox=(cx, cy, max(1, cw), max(1, ch)),
                        kind="subzone",
                    )
                )
                idx += 1
        return out

    @staticmethod
    def _lookup_knowledge(label: str, knowledge_map: Optional[Dict[str, str]]) -> str:
        if not knowledge_map:
            return ""
        needle = label.strip().lower()
        if needle in knowledge_map:
            return knowledge_map[needle]
        for key, desc in knowledge_map.items():
            if key.lower() in needle or needle in key.lower():
                return desc
        return ""
