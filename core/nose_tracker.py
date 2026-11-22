import math
import sys
import threading
import time
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal


class NoseTrackerWorker(QObject):
    """Tracks face movement on a webcam for responsive cursor control with no-webcam fallback."""

    delta_ready = Signal(int, int)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        gain_x: float = 95.0,
        gain_y: float = 85.0,
        deadzone: float = 0.018,
        smoothing: float = 0.65,
    ):
        super().__init__(None)
        self.gain_x = gain_x
        self.gain_y = gain_y
        self.deadzone = deadzone
        self.smoothing = smoothing

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
        self.status_changed.emit("Face center reset — look straight ahead.")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
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

    def _detect_face_normalized(self, frame, cv2, face_cascade) -> Optional[Tuple[float, float]]:
        small = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(45, 45))
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        face_cx = (fx + fw * 0.5) / 320.0
        face_cy = (fy + fh * 0.5) / 240.0
        mirrored_x = 1.0 - face_cx
        return mirrored_x, face_cy

    def _apply_accel(self, offset: float, gain: float) -> float:
        mag = abs(offset)
        if mag < self.deadzone:
            return 0.0
        effective = mag - self.deadzone
        # Non-linear boost: gentle for tiny tilts, fast sweep for larger head turns
        speed = (effective * gain) + ((effective * 14.0) ** 2)
        return math.copysign(speed, offset)

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

        self.status_changed.emit("Face tracking active (say 'recenter' anytime).")
        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.015)
                    continue

                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    self._anchor = None

                pos = self._detect_face_normalized(frame, cv2, face_cascade)
                if pos is None:
                    time.sleep(0.01)
                    continue

                if self._anchor is None:
                    self._anchor = pos
                    continue

                off_x = pos[0] - self._anchor[0]
                off_y = pos[1] - self._anchor[1]

                raw_dx = self._apply_accel(off_x, self.gain_x)
                raw_dy = self._apply_accel(off_y, self.gain_y)

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
