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
    """Recursive UI panel/group & scoped sub-region grounder (MS Office KeyTip style)."""

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
                cv2.rectangle(bgr, (rel_x1, rel_y1), (rel_x2, rel_y2), (25, 25, 32), -1)

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

    @staticmethod
    def _contains(outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int], pad: int = 6) -> bool:
        ox, oy, ow, oh = outer
        ix, iy, iw, ih = inner
        return (
            ix >= ox - pad
            and iy >= oy - pad
            and (ix + iw) <= (ox + ow + pad)
            and (iy + ih) <= (oy + oh + pad)
            and (iw * ih) < (ow * oh * 0.88)
        )

    @classmethod
    def _dedupe_boxes(
        cls, boxes: List[Tuple[int, int, int, int]], iou_threshold: float = 0.45
    ) -> List[Tuple[int, int, int, int]]:
        kept: List[Tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda r: r[2] * r[3], reverse=True):
            if any(cls._iou(box, ex) >= iou_threshold for ex in kept):
                continue
            kept.append(box)
        return kept

    def detect_panels(self, frame_bgr: np.ndarray, max_panels: int = 8) -> List[DetectedRegion]:
        """Detect distinct UI containers/groups without slicing across full-screen lines."""
        h, w = frame_bgr.shape[:2]
        if h < 50 or w < 50:
            return []

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 30, 105)

        # Group nearby UI edges into container blocks without merging the whole screen
        dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
        blocks = cv2.dilate(edges, dilate_k, iterations=2)
        contours, _ = cv2.findContours(blocks, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = max(3500, int(w * h * 0.015))
        max_area = int(w * h * 0.75)

        candidates: List[Tuple[int, int, int, int]] = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            is_side_rail = ch >= int(h * 0.25) and 28 <= cw <= int(w * 0.25) and area >= 2500
            is_top_bar = cw >= int(w * 0.25) and 28 <= ch <= int(h * 0.16) and area >= 2500
            if (min_area <= area <= max_area and cw >= 45 and ch >= 40) or is_side_rail or is_top_bar:
                candidates.append((x, y, cw, ch))

        deduped = self._dedupe_boxes(candidates, iou_threshold=0.45)

        # Remove huge parent boxes that swallow multiple smaller distinct groups
        filtered: List[Tuple[int, int, int, int]] = []
        for box in deduped:
            contained_count = sum(1 for other in deduped if other != box and self._contains(box, other))
            if contained_count >= 2 and (box[2] * box[3]) > int(w * h * 0.45):
                continue
            filtered.append(box)

        chosen = (filtered if filtered else deduped)[:max_panels]
        chosen.sort(key=lambda r: (r[1] // max(1, h // 4), r[0]))

        return [
            DetectedRegion(
                index=i + 1,
                label=f"Group {i + 1}",
                bbox=box,
                kind="panel",
            )
            for i, box in enumerate(chosen)
        ]

    def detect_sector_elements(
        self,
        frame_bgr: np.ndarray,
        sector_bbox: Tuple[int, int, int, int],
        knowledge_map: Optional[Dict[str, str]] = None,
        max_elements: int = 16,
    ) -> List[DetectedRegion]:
        """Detect sub-groups, buttons, and OCR text labels strictly inside sector_bbox."""
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
                        bw = max(14, max(xs) - min(xs))
                        bh = max(12, max(ys) - min(ys))
                        desc = self._lookup_knowledge(text, knowledge_map)
                        candidates.append((text, (bx, by, bw, bh), score, desc))
            except Exception:
                pass

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 130)
        dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (6, 6))
        dilated = cv2.dilate(edges, dilate_k, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_w = max(18, min(48, cw // 8))
        min_h = max(16, min(40, ch // 8))
        max_w = max(min_w + 10, int(cw * 0.85))
        max_h = max(min_h + 10, int(ch * 0.85))

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            if min_w <= rw <= max_w and min_h <= rh <= max_h:
                box = (x1 + rx, y1 + ry, rw, rh)
                if not any(self._iou(box, c[1]) > 0.35 for c in candidates):
                    candidates.append(("Item", box, 0.7, ""))

        deduped_items: List[Tuple[str, Tuple[int, int, int, int], float, str]] = []
        for item in sorted(candidates, key=lambda c: c[1][2] * c[1][3], reverse=True):
            if any(self._iou(item[1], ex[1]) > 0.45 for ex in deduped_items):
                continue
            deduped_items.append(item)

        deduped_items.sort(key=lambda c: (c[1][1] // max(18, ch // 6), c[1][0]))
        trimmed = deduped_items[:max_elements]

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
        """Split any target box into numbered sub-zones for recursive deeper drill-down."""
        x, y, w, h = bbox
        if w >= h * 2.2 and w >= 120:
            rows, cols = 1, 3
        elif h >= w * 2.2 and h >= 120:
            rows, cols = 3, 1
        else:
            rows, cols = rows, cols

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
                        label=f"Sub {idx}",
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
