import sys
import threading
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


class NoseTrackerWorker(QObject):
    """Tracks face movement with a 5-second guided calibration and maps neutral face to screen center."""

    screen_pos_ready = Signal(int, int)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        calibration_seconds: float = 30.0,
        smoothing: float = 0.35,
        right_boost: float = 1.25,
    ):
        super().__init__(None)
        self.screen_width = max(1, int(screen_width))
        self.screen_height = max(1, int(screen_height))
        self.calibration_seconds = max(2.0, float(calibration_seconds))
        self.smoothing = smoothing
        self.right_boost = right_boost

        self._stop_event = threading.Event()
        self._recenter_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._center_x = 0.5
        self._center_y = 0.5
        self._range_right = 0.14
        self._range_left = 0.14
        self._range_up = 0.12
        self._range_down = 0.12

        self._cur_x = float(self.screen_width) * 0.5
        self._cur_y = float(self.screen_height) * 0.5

    def recenter(self) -> None:
        self._recenter_event.set()
        self.status_changed.emit("Starting 30s calibration — look center first...")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._recenter_event.clear()
        self._cur_x = float(self.screen_width) * 0.5
        self._cur_y = float(self.screen_height) * 0.5
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

    def _detect_face_normalized(self, frame, cv2, face_cascade) -> Optional[Tuple[float, float]]:
        small = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(45, 45))
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        face_cx = (fx + fw * 0.5) / 320.0
        face_cy = (fy + fh * 0.5) / 240.0
        # Mirror horizontally so moving face right on neck moves right
        mirrored_x = 1.0 - face_cx
        return mirrored_x, face_cy

    def _run_calibration(self, cap, cv2, face_cascade) -> bool:
        start_t = time.monotonic()
        center_samples: List[Tuple[float, float]] = []
        max_dx_right = 0.06
        max_dx_left = 0.06
        max_dy_up = 0.06
        max_dy_down = 0.06
        last_prompt = ""

        while not self._stop_event.is_set():
            elapsed = time.monotonic() - start_t
            remaining = max(0.0, self.calibration_seconds - elapsed)
            if elapsed >= self.calibration_seconds:
                break

            if elapsed < 7.0:
                stage = "center"
                prompt = f"Calibrating ({remaining:.1f}s): Hold face CENTER (screen middle)"
            elif elapsed < 14.0:
                stage = "right"
                prompt = f"Calibrating ({remaining:.1f}s): Slowly move face RIGHT on neck"
            elif elapsed < 21.0:
                stage = "left"
                prompt = f"Calibrating ({remaining:.1f}s): Slowly move face LEFT on neck"
            elif elapsed < 26.0:
                stage = "up"
                prompt = f"Calibrating ({remaining:.1f}s): Slowly tilt face UP"
            else:
                stage = "down"
                prompt = f"Calibrating ({remaining:.1f}s): Slowly tilt face DOWN"

            if prompt != last_prompt:
                self.status_changed.emit(prompt)
                last_prompt = prompt

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.015)
                continue

            pos = self._detect_face_normalized(frame, cv2, face_cascade)
            if pos is not None:
                if stage == "center":
                    center_samples.append(pos)
                else:
                    if not center_samples:
                        center_samples.append(pos)
                    cx = sum(p[0] for p in center_samples) / len(center_samples)
                    cy = sum(p[1] for p in center_samples) / len(center_samples)
                    dx = pos[0] - cx
                    dy = pos[1] - cy
                    if stage == "right" and dx > 0:
                        max_dx_right = max(max_dx_right, dx)
                    elif stage == "left" and dx < 0:
                        max_dx_left = max(max_dx_left, abs(dx))
                    elif stage == "up" and dy < 0:
                        max_dy_up = max(max_dy_up, abs(dy))
                    elif stage == "down" and dy > 0:
                        max_dy_down = max(max_dy_down, dy)

            time.sleep(0.02)

        if self._stop_event.is_set():
            return False

        if center_samples:
            self._center_x = sum(p[0] for p in center_samples) / len(center_samples)
            self._center_y = sum(p[1] for p in center_samples) / len(center_samples)

        # Slightly tighten effective span so full screen is reachable without straining neck
        self._range_right = max(0.04, max_dx_right * 0.85)
        self._range_left = max(0.04, max_dx_left * 0.85)
        self._range_up = max(0.04, max_dy_up * 0.85)
        self._range_down = max(0.04, max_dy_down * 0.85)

        self._cur_x = float(self.screen_width) * 0.5
        self._cur_y = float(self.screen_height) * 0.5
        self.screen_pos_ready.emit(int(self._cur_x), int(self._cur_y))
        self.status_changed.emit("Calibration complete! Center face = screen center.")
        return True

    def _map_to_screen(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        dx = pos[0] - self._center_x
        dy = pos[1] - self._center_y

        # Small deadzone near neutral center
        if abs(dx) < 0.01:
            dx = 0.0
        if abs(dy) < 0.01:
            dy = 0.0

        if dx >= 0:
            norm_x = min(1.0, (dx * self.right_boost) / self._range_right)
        else:
            norm_x = -min(1.0, abs(dx) / self._range_left)

        if dy >= 0:
            norm_y = min(1.0, dy / self._range_down)
        else:
            norm_y = -min(1.0, abs(dy) / self._range_up)

        half_w = float(self.screen_width) * 0.5
        half_h = float(self.screen_height) * 0.5

        target_x = half_w + (norm_x * half_w)
        target_y = half_h + (norm_y * half_h)

        self._cur_x += (target_x - self._cur_x) * self.smoothing
        self._cur_y += (target_y - self._cur_y) * self.smoothing

        ix = max(0, min(self.screen_width - 1, int(round(self._cur_x))))
        iy = max(0, min(self.screen_height - 1, int(round(self._cur_y))))
        return ix, iy

    def _run_loop(self) -> None:
        try:
            import cv2
        except Exception as exc:
            self.error_occurred.emit(f"Webcam tracking unavailable ('cv2' missing): {exc}")
            return

        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        except Exception:
            cascade_path = None

        face_cascade = cv2.CascadeClassifier(cascade_path) if cascade_path else None
        if face_cascade is None or face_cascade.empty():
            self.error_occurred.emit("Face detector unavailable; use voice cursor commands instead.")
            return

        cap, first_frame = self._open_camera(cv2)
        if cap is None or first_frame is None:
            self.status_changed.emit("No webcam detected — voice cursor ('move left/right/up/down', 'click') active.")
            return

        try:
            if not self._run_calibration(cap, cv2, face_cascade):
                return

            while not self._stop_event.is_set():
                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    if not self._run_calibration(cap, cv2, face_cascade):
                        return

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.015)
                    continue

                pos = self._detect_face_normalized(frame, cv2, face_cascade)
                if pos is not None:
                    sx, sy = self._map_to_screen(pos)
                    self.screen_pos_ready.emit(sx, sy)

                time.sleep(0.01)
        except Exception as exc:
            self.error_occurred.emit(f"Face tracker stopped ({exc}); voice cursor still works.")
        finally:
            cap.release()
