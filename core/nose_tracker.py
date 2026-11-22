import math
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


class NoseTrackerWorker(QObject):
    """Checks multi-angle face visibility before calibrating, then moves cursor linearly via relative deltas."""

    delta_ready = Signal(int, int)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        gain_x: float = 95.0,
        gain_y: float = 85.0,
        deadzone: float = 0.018,
        smoothing: float = 0.65,
        right_boost: float = 1.25,
    ):
        super().__init__(None)
        self.gain_x = gain_x
        self.gain_y = gain_y
        self.deadzone = deadzone
        self.smoothing = smoothing
        self.right_boost = right_boost

        self._stop_event = threading.Event()
        self._recenter_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._anchor: Optional[Tuple[float, float]] = None
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._rem_x = 0.0
        self._rem_y = 0.0

    def recenter(self) -> None:
        self._anchor = None
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._rem_x = 0.0
        self._rem_y = 0.0
        self._recenter_event.set()
        self.status_changed.emit("Re-checking face visibility before calibration...")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._recenter_event.clear()
        self._anchor = None
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._rem_x = 0.0
        self._rem_y = 0.0
        self._thread = threading.Thread(target=self._run_loop, name="FaceTrackerThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _open_camera(self, cv2):
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        for idx in range(3):
            cap = cv2.VideoCapture(idx, backend)
            if cap is not None and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 60)
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    return cap, frame
            if cap is not None:
                cap.release()
        return None, None

    def _load_cascades(self, cv2):
        cascades = []
        try:
            base = cv2.data.haarcascades
            for fname in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
                c = cv2.CascadeClassifier(base + fname)
                if c is not None and not c.empty():
                    cascades.append((fname, c))
        except Exception:
            pass
        return cascades

    def _detect_face_normalized(self, frame, cv2, cascades) -> Optional[Tuple[float, float]]:
        small = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        flipped_gray = cv2.flip(gray, 1)

        best_box = None
        best_area = 0
        best_flipped = False

        for fname, cascade in cascades:
            faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=3, minSize=(40, 40))
            for (fx, fy, fw, fh) in faces:
                area = fw * fh
                if area > best_area:
                    best_area = area
                    best_box = (fx, fy, fw, fh)
                    best_flipped = False

            if "profile" in fname:
                pfaces = cascade.detectMultiScale(flipped_gray, scaleFactor=1.12, minNeighbors=3, minSize=(40, 40))
                for (fx, fy, fw, fh) in pfaces:
                    area = fw * fh
                    if area > best_area:
                        best_area = area
                        best_box = (320 - (fx + fw), fy, fw, fh)
                        best_flipped = True

        if best_box is None:
            return None

        fx, fy, fw, fh = best_box
        face_cx = (fx + fw * 0.5) / 320.0
        face_cy = (fy + fh * 0.5) / 240.0
        mirrored_x = 1.0 - face_cx
        _ = best_flipped
        return mirrored_x, face_cy

    def _verify_all_directions(self, cap, cv2, cascades) -> Optional[Tuple[float, float]]:
        """Confirm face is clearly detected across center, right, left, up, and down turns."""
        checks = [
            ("center", "Visibility check: Hold face CENTER so camera sees you clearly..."),
            ("right", "Visibility check: Turn/tilt face RIGHT to confirm tracking..."),
            ("left", "Visibility check: Turn/tilt face LEFT to confirm tracking..."),
            ("up", "Visibility check: Tilt face UP to confirm tracking..."),
            ("down", "Visibility check: Tilt face DOWN to confirm tracking..."),
        ]
        seen: Dict[str, List[Tuple[float, float]]] = {k: [] for k, _ in checks}
        baseline: Optional[Tuple[float, float]] = None

        for step_key, prompt in checks:
            self.status_changed.emit(prompt)
            confirmed_hits = 0
            start_step = time.monotonic()

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    return self._verify_all_directions(cap, cv2, cascades)

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.015)
                    continue

                pos = self._detect_face_normalized(frame, cv2, cascades)
                if pos is None:
                    if time.monotonic() - start_step > 4.0:
                        self.status_changed.emit(f"{prompt} (face not clearly visible — adjust angle/light)")
                        start_step = time.monotonic()
                    time.sleep(0.015)
                    continue

                if baseline is None and step_key == "center":
                    seen["center"].append(pos)
                    confirmed_hits += 1
                    if confirmed_hits >= 5:
                        baseline = (
                            sum(p[0] for p in seen["center"]) / len(seen["center"]),
                            sum(p[1] for p in seen["center"]) / len(seen["center"]),
                        )
                        break
                else:
                    bx, by = baseline if baseline is not None else pos
                    dx = pos[0] - bx
                    dy = pos[1] - by
                    moved_ok = (
                        (step_key == "right" and dx > 0.025)
                        or (step_key == "left" and dx < -0.025)
                        or (step_key == "up" and dy < -0.02)
                        or (step_key == "down" and dy > 0.02)
                    )
                    if moved_ok:
                        seen[step_key].append(pos)
                        confirmed_hits += 1
                        if confirmed_hits >= 3:
                            break
                    elif time.monotonic() - start_step > 6.0:
                        # Accept visible detection after timeout so user isn't stuck if movement is subtle
                        seen[step_key].append(pos)
                        break

                time.sleep(0.02)

            if self._stop_event.is_set():
                return None

        if seen["center"]:
            return (
                sum(p[0] for p in seen["center"]) / len(seen["center"]),
                sum(p[1] for p in seen["center"]) / len(seen["center"]),
            )
        return baseline or (0.5, 0.5)

    def _run_calibration(self, cap, cv2, cascades) -> bool:
        anchor = self._verify_all_directions(cap, cv2, cascades)
        if anchor is None or self._stop_event.is_set():
            return False

        self.status_changed.emit("Visibility confirmed! Calibrating neutral center (3s)...")
        samples: List[Tuple[float, float]] = [anchor]
        end_t = time.monotonic() + 3.0

        while not self._stop_event.is_set() and time.monotonic() < end_t:
            ok, frame = cap.read()
            if ok and frame is not None:
                pos = self._detect_face_normalized(frame, cv2, cascades)
                if pos is not None:
                    samples.append(pos)
            time.sleep(0.02)

        if self._stop_event.is_set():
            return False

        self._anchor = (
            sum(p[0] for p in samples) / len(samples),
            sum(p[1] for p in samples) / len(samples),
        )
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._rem_x = 0.0
        self._rem_y = 0.0
        self.status_changed.emit("Linear face tracking active (say 'recenter' anytime).")
        return True

    def _linear_step(self, offset: float, gain: float) -> float:
        mag = abs(offset)
        if mag < self.deadzone:
            return 0.0
        effective = mag - self.deadzone
        return math.copysign(effective * gain, offset)

    def _run_loop(self) -> None:
        try:
            import cv2
        except Exception as exc:
            self.error_occurred.emit(f"Webcam tracking unavailable ('cv2' missing): {exc}")
            return

        cascades = self._load_cascades(cv2)
        if not cascades:
            self.error_occurred.emit("Face detector unavailable; use voice cursor commands instead.")
            return

        cap, first_frame = self._open_camera(cv2)
        if cap is None or first_frame is None:
            self.status_changed.emit("No webcam detected — voice cursor ('move left/right/up/down', 'click') active.")
            return

        try:
            if not self._run_calibration(cap, cv2, cascades):
                return

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    if not self._run_calibration(cap, cv2, cascades):
                        return

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.015)
                    continue

                pos = self._detect_face_normalized(frame, cv2, cascades)
                if pos is None or self._anchor is None:
                    time.sleep(0.01)
                    continue

                off_x = pos[0] - self._anchor[0]
                off_y = pos[1] - self._anchor[1]
                eff_gain_x = self.gain_x * (self.right_boost if off_x > 0 else 1.0)

                raw_dx = self._linear_step(off_x, eff_gain_x)
                raw_dy = self._linear_step(off_y, self.gain_y)

                self._smooth_dx += (raw_dx - self._smooth_dx) * self.smoothing
                self._smooth_dy += (raw_dy - self._smooth_dy) * self.smoothing

                total_x = self._smooth_dx + self._rem_x
                total_y = self._smooth_dy + self._rem_y

                dx_int = int(round(total_x))
                dy_int = int(round(total_y))
                self._rem_x = total_x - dx_int
                self._rem_y = total_y - dy_int

                if dx_int != 0 or dy_int != 0:
                    self.delta_ready.emit(dx_int, dy_int)

                time.sleep(0.01)
        except Exception as exc:
            self.error_occurred.emit(f"Face tracker stopped ({exc}); voice cursor still works.")
        finally:
            cap.release()
