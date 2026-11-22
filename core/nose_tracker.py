import math
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


class NoseTrackerWorker(QObject):
    """Slow, patient multi-angle face check + neutral calibration with linear relative cursor control."""

    delta_ready = Signal(int, int)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    calibration_state_changed = Signal(bool)

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
        self.status_changed.emit("Restarting slow calibration (ignoring mic noise)...")

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
        self.calibration_state_changed.emit(False)
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

        for fname, cascade in cascades:
            faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=3, minSize=(40, 40))
            for (fx, fy, fw, fh) in faces:
                area = fw * fh
                if area > best_area:
                    best_area = area
                    best_box = (fx, fy, fw, fh)

            if "profile" in fname:
                pfaces = cascade.detectMultiScale(flipped_gray, scaleFactor=1.12, minNeighbors=3, minSize=(40, 40))
                for (fx, fy, fw, fh) in pfaces:
                    area = fw * fh
                    if area > best_area:
                        best_area = area
                        best_box = (320 - (fx + fw), fy, fw, fh)

        if best_box is None:
            return None

        fx, fy, fw, fh = best_box
        face_cx = (fx + fw * 0.5) / 320.0
        face_cy = (fy + fh * 0.5) / 240.0
        mirrored_x = 1.0 - face_cx
        return mirrored_x, face_cy

    def _wait_for_direction_hold(
        self,
        cap,
        cv2,
        cascades,
        step_key: str,
        label: str,
        baseline: Optional[Tuple[float, float]],
        required_hits: int = 20,
    ) -> Optional[List[Tuple[float, float]]]:
        """Patiently wait without timing out until user holds the requested head angle steadily."""
        samples: List[Tuple[float, float]] = []
        last_status = ""

        while not self._stop_event.is_set():
            if self._recenter_event.is_set():
                return None

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.03)
                continue

            pos = self._detect_face_normalized(frame, cv2, cascades)
            if pos is None:
                msg = f"{label} — waiting to see face clearly (ignoring audio noise)..."
                if msg != last_status:
                    self.status_changed.emit(msg)
                    last_status = msg
                time.sleep(0.04)
                continue

            if step_key == "center":
                # Check steadiness relative to recent samples so user settles calmly
                if samples:
                    avg_x = sum(p[0] for p in samples) / len(samples)
                    avg_y = sum(p[1] for p in samples) / len(samples)
                    if abs(pos[0] - avg_x) > 0.035 or abs(pos[1] - avg_y) > 0.035:
                        samples.clear()
                samples.append(pos)
            else:
                bx, by = baseline if baseline is not None else pos
                dx = pos[0] - bx
                dy = pos[1] - by
                in_direction = (
                    (step_key == "right" and dx > 0.028)
                    or (step_key == "left" and dx < -0.028)
                    or (step_key == "up" and dy < -0.022)
                    or (step_key == "down" and dy > 0.022)
                )
                if in_direction:
                    samples.append(pos)
                else:
                    # Gently decay rather than harshly resetting, and keep waiting patiently
                    if samples:
                        samples.pop()

            pct = min(100, int((len(samples) / required_hits) * 100))
            msg = f"{label}: {pct}% (take your time — ignoring audio noise)"
            if msg != last_status:
                self.status_changed.emit(msg)
                last_status = msg

            if len(samples) >= required_hits:
                self.status_changed.emit(f"{label}: Done! Relax back to center...")
                time.sleep(0.7)
                return samples

            time.sleep(0.045)

        return None

    def _run_calibration(self, cap, cv2, cascades) -> bool:
        self.calibration_state_changed.emit(True)
        try:
            self.status_changed.emit("Slow calibration starting — take your time, mic noise is ignored.")
            time.sleep(0.8)

            center_samples = self._wait_for_direction_hold(
                cap, cv2, cascades, "center", "Step 1/5: Hold face steady at CENTER", None, required_hits=24
            )
            if center_samples is None:
                return False

            baseline = (
                sum(p[0] for p in center_samples) / len(center_samples),
                sum(p[1] for p in center_samples) / len(center_samples),
            )

            directional_steps = [
                ("right", "Step 2/5: Slowly turn/tilt RIGHT & hold"),
                ("left", "Step 3/5: Slowly turn/tilt LEFT & hold"),
                ("up", "Step 4/5: Slowly tilt UP & hold"),
                ("down", "Step 5/5: Slowly tilt DOWN & hold"),
            ]

            for step_key, label in directional_steps:
                res = self._wait_for_direction_hold(
                    cap, cv2, cascades, step_key, label, baseline, required_hits=18
                )
                if res is None:
                    return False

            # Final calm 30-second neutral center lock
            final_samples: List[Tuple[float, float]] = []
            start_lock = time.monotonic()
            lock_duration = 30.0
            last_sec = -1

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    return False
                elapsed = time.monotonic() - start_lock
                rem = max(0.0, lock_duration - elapsed)
                if elapsed >= lock_duration and len(final_samples) >= 20:
                    break

                ok, frame = cap.read()
                if ok and frame is not None:
                    pos = self._detect_face_normalized(frame, cv2, cascades)
                    if pos is not None:
                        final_samples.append(pos)

                sec_ceil = int(math.ceil(rem))
                pct = min(100, int((elapsed / lock_duration) * 100))
                if sec_ceil != last_sec:
                    self.status_changed.emit(
                        f"Final lock ({sec_ceil}s left, {pct}%): Relax & hold CENTER (ignoring mic noise)..."
                    )
                    last_sec = sec_ceil
                time.sleep(0.04)

            if self._stop_event.is_set():
                return False

            self._anchor = (
                sum(p[0] for p in final_samples) / len(final_samples),
                sum(p[1] for p in final_samples) / len(final_samples),
            )
            self._smooth_dx = 0.0
            self._smooth_dy = 0.0
            self._rem_x = 0.0
            self._rem_y = 0.0
            self.status_changed.emit("Calibration complete! Linear cursor + voice active.")
            return True
        finally:
            self.calibration_state_changed.emit(False)

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
            while not self._stop_event.is_set():
                self._recenter_event.clear()
                if self._run_calibration(cap, cv2, cascades):
                    break
                if self._stop_event.is_set():
                    return

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    while not self._stop_event.is_set():
                        self._recenter_event.clear()
                        if self._run_calibration(cap, cv2, cascades):
                            break

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
            self.calibration_state_changed.emit(False)
            cap.release()
