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
    bbox: Tuple[int, int, int, int]  # (x, y, w, h) in physical capture pixels
    kind: str = "panel"  # "panel" | "element" | "subzone"
    role: str = "Panel"  # "Button" | "Slider" | "Timeline" | "Zoomable" | "Panel"
    can_zoom: bool = False
    confidence: float = 1.0
    description: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Tuple[int, int]:
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)


class VisionGrounder:
    """GUI-agnostic visual segmenter and interactable classifier (Button, Slider, Timeline, Zoomable, Panel)."""

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
                median_color = np.median(bgr.reshape(-1, 3), axis=0).astype(np.uint8).tolist()
                cv2.rectangle(bgr, (rel_x1, rel_y1), (rel_x2, rel_y2), median_color, -1)

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
    def _dedupe_boxes(
        cls, boxes: List[Tuple[int, int, int, int]], iou_threshold: float = 0.42
    ) -> List[Tuple[int, int, int, int]]:
        kept: List[Tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda r: r[2] * r[3], reverse=True):
            if any(cls._iou(box, ex) >= iou_threshold for ex in kept):
                continue
            kept.append(box)
        return kept

    @staticmethod
    def classify_region(
        frame_bgr: np.ndarray,
        bbox: Tuple[int, int, int, int],
        is_top_level: bool = False,
    ) -> Tuple[str, bool, str]:
        """Infer interactable role ('Button', 'Slider', 'Timeline', 'Zoomable', 'Panel'), zoomability, and hint."""
        x, y, w, h = bbox
        fh, fw = frame_bgr.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(fw, x + w)
        y2 = min(fh, y + h)

        aspect_wh = w / max(1.0, float(h))
        aspect_hw = h / max(1.0, float(w))
        area_ratio = (w * h) / max(1.0, float(fw * fh))

        edge_density = 0.0
        if x2 > x1 + 4 and y2 > y1 + 4:
            sub_gray = cv2.cvtColor(frame_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            sub_edges = cv2.Canny(sub_gray, 40, 120)
            edge_density = float(np.mean(sub_edges > 0))

        # Horizontal or vertical slider/scrubber track
        if (aspect_wh >= 4.5 and h <= max(38, int(fh * 0.045)) and w >= 48) or (
            aspect_hw >= 4.5 and w <= max(38, int(fw * 0.045)) and h >= 48
        ):
            return (
                "Slider",
                False,
                "Slider/scrubber track — hover and use 'hover left/right', 'nudge', or 'drag' to adjust.",
            )

        # Wide multi-track / timeline / dense region suitable for zooming
        if w >= int(fw * 0.35) and h >= max(65, int(fh * 0.10)) and (aspect_wh >= 2.2 or edge_density >= 0.04):
            return (
                "Timeline",
                True,
                "Wide timeline/track region — drill down or say 'zoom' for fine horizontal scrubbing and clip placement.",
            )

        # Compact / card / pill control -> Button
        if not is_top_level and area_ratio < 0.08 and 0.22 <= aspect_wh <= 6.0 and w >= 16 and h >= 14:
            can_zoom = (w >= 90 and h >= 55) or edge_density >= 0.08
            hint = "Button/control — hover to inspect or say 'click' to activate."
            if can_zoom:
                hint += " Say 'zoom' if you need finer sub-spots."
            return ("Button", can_zoom, hint)

        # Larger container or top-level sector
        can_zoom = (w * h) >= max(4000, int(fw * fh * 0.03))
        role = "Panel" if is_top_level or area_ratio >= 0.06 else "Zoomable"
        hint = (
            "Container group — drill down to inspect controls inside, or say 'zoom' for sub-zones."
            if can_zoom
            else "Interactive region — hover, drill down, or say 'click'."
        )
        return (role, can_zoom, hint)

    def detect_panels(self, frame_bgr: np.ndarray, max_panels: int = 8) -> List[DetectedRegion]:
        """Dynamically segment distinct UI containers/regions on any foreground GUI."""
        h, w = frame_bgr.shape[:2]
        if h < 60 or w < 60:
            return []

        scale = 0.25
        small = cv2.resize(
            frame_bgr, (max(40, int(w * scale)), max(40, int(h * scale))), interpolation=cv2.INTER_AREA
        )

        quant = (small // 12) * 12
        flat = quant.reshape(-1, 3)
        colors, counts = np.unique(flat, axis=0, return_counts=True)
        top_idx = np.argsort(-counts)[:12]

        raw_boxes: List[Tuple[int, int, int, int]] = []
        min_area = max(2200, int(w * h * 0.012))
        max_area = int(w * h * 0.72)

        for idx in top_idx:
            col = colors[idx]
            mask = (np.all(np.abs(quant.astype(np.int16) - col.astype(np.int16)) <= 12, axis=2)).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                sx, sy, scw, sch = cv2.boundingRect(cnt)
                x = int(round(sx / scale))
                y = int(round(sy / scale))
                cw = min(w - x, int(round(scw / scale)))
                ch = min(h - y, int(round(sch / scale)))
                area = cw * ch
                is_rail = ch >= int(h * 0.22) and 24 <= cw <= int(w * 0.24) and area >= 1800
                is_bar = cw >= int(w * 0.22) and 24 <= ch <= int(h * 0.16) and area >= 1800
                if (min_area <= area <= max_area and cw >= 40 and ch >= 36) or is_rail or is_bar:
                    raw_boxes.append((x, y, cw, ch))

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 35, 110)
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=1)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            if min_area <= area <= max_area and cw >= 45 and ch >= 40:
                raw_boxes.append((x, y, cw, ch))

        deduped = self._dedupe_boxes(raw_boxes, iou_threshold=0.40)
        deduped.sort(key=lambda r: (r[1] // max(1, h // 4), r[0]))
        chosen = deduped[:max_panels]

        regions: List[DetectedRegion] = []
        for i, box in enumerate(chosen):
            role, can_zoom, hint = self.classify_region(frame_bgr, box, is_top_level=True)
            regions.append(
                DetectedRegion(
                    index=i + 1,
                    label=f"{role} {i + 1}",
                    bbox=box,
                    kind="panel",
                    role=role,
                    can_zoom=can_zoom,
                    description=hint,
                )
            )
        return regions

    def detect_sector_elements(
        self,
        frame_bgr: np.ndarray,
        sector_bbox: Tuple[int, int, int, int],
        knowledge_map: Optional[Dict[str, str]] = None,
        max_elements: int = 16,
    ) -> List[DetectedRegion]:
        """Detect interactable controls, sliders, OCR labels, and sub-regions inside sector_bbox."""
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
        candidates: List[Tuple[str, Tuple[int, int, int, int], float, str, str, bool]] = []

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
                        bw = max(16, max(xs) - min(xs))
                        bh = max(14, max(ys) - min(ys))
                        role, can_zoom, hint = self.classify_region(frame_bgr, (bx, by, bw, bh), is_top_level=False)
                        if role == "Panel":
                            role = "Button"
                        kb = self._lookup_knowledge(text, knowledge_map)
                        desc = f"{kb} ({hint})" if kb else hint
                        candidates.append((text, (bx, by, bw, bh), score, desc, role, can_zoom))
            except Exception:
                pass

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 35, 120)
        dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (6, 6))
        dilated = cv2.dilate(edges, dilate_k, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_w = max(16, min(36, cw // 12))
        min_h = max(14, min(32, ch // 12))
        max_w = max(min_w + 10, int(cw * 0.95))
        max_h = max(min_h + 10, int(ch * 0.90))

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            if min_w <= rw <= max_w and min_h <= rh <= max_h:
                box = (x1 + rx, y1 + ry, rw, rh)
                if not any(self._iou(box, c[1]) > 0.36 for c in candidates):
                    role, can_zoom, hint = self.classify_region(frame_bgr, box, is_top_level=False)
                    candidates.append((role, box, 0.75, hint, role, can_zoom))

        deduped: List[Tuple[str, Tuple[int, int, int, int], float, str, str, bool]] = []
        for item in sorted(candidates, key=lambda c: c[1][2] * c[1][3], reverse=True):
            if any(self._iou(item[1], ex[1]) > 0.42 for ex in deduped):
                continue
            deduped.append(item)

        deduped.sort(key=lambda c: (c[1][1] // max(20, ch // 6), c[1][0]))
        trimmed = deduped[:max_elements]

        out: List[DetectedRegion] = []
        role_counts: Dict[str, int] = {}
        for idx, (label, box, conf, desc, role, can_zoom) in enumerate(trimmed):
            role_counts[role] = role_counts.get(role, 0) + 1
            display_label = label if label != role else f"{role} {role_counts[role]}"
            out.append(
                DetectedRegion(
                    index=idx + 1,
                    label=display_label,
                    bbox=box,
                    kind="element",
                    role=role,
                    can_zoom=can_zoom,
                    confidence=conf,
                    description=desc,
                )
            )
        return out

    @staticmethod
    def subdivide_box(
        bbox: Tuple[int, int, int, int], rows: int = 2, cols: int = 2
    ) -> List[DetectedRegion]:
        """Split a target box into numbered sub-zones for fine hovering/clicking."""
        x, y, w, h = bbox
        if w >= h * 2.4 and w >= 140:
            rows, cols = 1, 3
        elif h >= w * 2.4 and h >= 140:
            rows, cols = 3, 1

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
                        label=f"Zoom {idx}",
                        bbox=(cx, cy, max(1, cw), max(1, ch)),
                        kind="subzone",
                        role="Zoomable",
                        can_zoom=True,
                        description="Zoom sub-zone — hover to inspect or say 'click' to activate.",
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
