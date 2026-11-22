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
        self._prev_off_x = 0.0
        self._prev_off_y = 0.0
        self.max_step = 6

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
            total_seconds = 60.0
            stages = [
                ("center", "1/9 CENTER", "Hold face steady at CENTER"),
                ("right", "2/9 RIGHT", "Slowly turn/tilt RIGHT"),
                ("left", "3/9 LEFT", "Slowly turn/tilt LEFT"),
                ("up", "4/9 UP", "Slowly tilt UP"),
                ("down", "5/9 DOWN", "Slowly tilt DOWN"),
                ("nw", "6/9 NW", "Slowly turn/tilt UP-LEFT (NW)"),
                ("ne", "7/9 NE", "Slowly turn/tilt UP-RIGHT (NE)"),
                ("sw", "8/9 SW", "Slowly turn/tilt DOWN-LEFT (SW)"),
                ("se", "9/9 SE", "Slowly turn/tilt DOWN-RIGHT (SE)"),
            ]
            slot_seconds = total_seconds / float(len(stages))

            start_t = time.monotonic()
            center_samples: List[Tuple[float, float]] = []
            all_samples: List[Tuple[float, float]] = []
            last_label = ""

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    return False

                elapsed = time.monotonic() - start_t
                if elapsed >= total_seconds:
                    break

                idx = min(len(stages) - 1, int(elapsed // slot_seconds))
                stage_key, stage_title, instruction = stages[idx]
                stage_elapsed = elapsed - (idx * slot_seconds)
                stage_rem = max(0.0, slot_seconds - stage_elapsed)
                total_rem = max(0.0, total_seconds - elapsed)

                status_line = (
                    f"[{stage_title} | Stage {stage_rem:.1f}s | Total {total_rem:.1f}s]: "
                    f"{instruction} — ignoring mic noise"
                )
                if status_line != last_label:
                    self.status_changed.emit(status_line)
                    last_label = status_line

                ok, frame = cap.read()
                if ok and frame is not None:
                    pos = self._detect_face_normalized(frame, cv2, cascades)
                    if pos is not None:
                        all_samples.append(pos)
                        if stage_key == "center":
                            center_samples.append(pos)

                time.sleep(0.03)

            if self._stop_event.is_set():
                return False

            if center_samples:
                self._anchor = (
                    sum(p[0] for p in center_samples) / len(center_samples),
                    sum(p[1] for p in center_samples) / len(center_samples),
                )
            elif all_samples:
                self._anchor = (
                    sum(p[0] for p in all_samples) / len(all_samples),
                    sum(p[1] for p in all_samples) / len(all_samples),
                )
            else:
                self._anchor = (0.5, 0.5)

            self._smooth_dx = 0.0
            self._smooth_dy = 0.0
            self._rem_x = 0.0
            self._rem_y = 0.0
            self._prev_off_x = 0.0
            self._prev_off_y = 0.0
            self.status_changed.emit("1-min calibration complete! Linear cursor + voice active.")
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

                # Gently adapt anchor when head is nearly back to center so posture doesn't pull to corner
                if abs(off_x) < 0.032 and abs(off_y) < 0.032:
                    self._anchor = (
                        self._anchor[0] + (pos[0] - self._anchor[0]) * 0.015,
                        self._anchor[1] + (pos[1] - self._anchor[1]) * 0.015,
                    )
                    off_x = pos[0] - self._anchor[0]
                    off_y = pos[1] - self._anchor[1]

                # Dampen continuous drift when holding a static angle (little change from previous offset)
                vel_x = abs(off_x - self._prev_off_x)
                vel_y = abs(off_y - self._prev_off_y)
                self._prev_off_x = off_x
                self._prev_off_y = off_y

                hold_scale_x = 1.0 if vel_x > 0.004 else 0.25
                hold_scale_y = 1.0 if vel_y > 0.004 else 0.25

                eff_gain_x = self.gain_x * (self.right_boost if off_x > 0 else 1.0) * 0.55 * hold_scale_x
                eff_gain_y = self.gain_y * 0.55 * hold_scale_y

                raw_dx = self._linear_step(off_x, eff_gain_x)
                raw_dy = self._linear_step(off_y, eff_gain_y)

                self._smooth_dx += (raw_dx - self._smooth_dx) * 0.45
                self._smooth_dy += (raw_dy - self._smooth_dy) * 0.45

                total_x = self._smooth_dx + self._rem_x
                total_y = self._smooth_dy + self._rem_y

                dx_int = max(-self.max_step, min(self.max_step, int(round(total_x))))
                dy_int = max(-self.max_step, min(self.max_step, int(round(total_y))))
                self._rem_x = max(-2.0, min(2.0, total_x - dx_int))
                self._rem_y = max(-2.0, min(2.0, total_y - dy_int))

                if dx_int != 0 or dy_int != 0:
                    self.delta_ready.emit(dx_int, dy_int)

                time.sleep(0.01)
        except Exception as exc:
            self.error_occurred.emit(f"Face tracker stopped ({exc}); voice cursor still works.")
        finally:
            self.calibration_state_changed.emit(False)
            cap.release()
