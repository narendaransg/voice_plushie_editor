import sys
import threading
import time
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal


class NoseTrackerWorker(QObject):
    """Tracks nose-tip displacement on a webcam with graceful no-webcam fallback."""

    delta_ready = Signal(int, int)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        gain_x: float = 28.0,
        gain_y: float = 24.0,
        deadzone: float = 0.035,
        smoothing: float = 0.35,
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

    def recenter(self) -> None:
        self._anchor = None
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._recenter_event.set()
        self.status_changed.emit("Nose anchor reset — look straight ahead.")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._anchor = None
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._thread = threading.Thread(target=self._run_loop, name="NoseTrackerThread", daemon=True)
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
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    return cap, frame
            if cap is not None:
                cap.release()
        return None, None

    def _detect_nose_normalized(self, frame, cv2, face_cascade) -> Optional[Tuple[float, float]]:
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        # Pick largest face
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        # Approximate nose tip near center-lower-mid of detected face box
        nose_x = (fx + fw * 0.5) / float(w)
        nose_y = (fy + fh * 0.55) / float(h)
        # Mirror horizontal movement so moving head right moves cursor right
        mirrored_x = 1.0 - nose_x
        return mirrored_x, nose_y

    def _run_loop(self) -> None:
        try:
            import cv2
        except Exception as exc:
            self.error_occurred.emit(f"Webcam tracking unavailable ('cv2' missing): {exc}")
            return

        cascade_path = Path_cascade = None
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

        self.status_changed.emit("Nose tracking active (say 'recenter' anytime).")
        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.05)
                    continue

                if self._recenter_event.is_set():
                    self._recenter_event.clear()
                    self._anchor = None

                pos = self._detect_nose_normalized(frame, cv2, face_cascade)
                if pos is None:
                    time.sleep(0.02)
                    continue

                if self._anchor is None:
                    self._anchor = pos
                    continue

                raw_dx = (pos[0] - self._anchor[0]) * self.gain_x
                raw_dy = (pos[1] - self._anchor[1]) * self.gain_y

                if abs(pos[0] - self._anchor[0]) < self.deadzone:
                    raw_dx = 0.0
                if abs(pos[1] - self._anchor[1]) < self.deadzone:
                    raw_dy = 0.0

                self._smooth_dx += (raw_dx - self._smooth_dx) * self.smoothing
                self._smooth_dy += (raw_dy - self._smooth_dy) * self.smoothing

                dx_int = int(round(self._smooth_dx))
                dy_int = int(round(self._smooth_dy))
                if dx_int != 0 or dy_int != 0:
                    self.delta_ready.emit(dx_int, dy_int)

                time.sleep(0.025)
        except Exception as exc:
            self.error_occurred.emit(f"Nose tracker stopped ({exc}); voice cursor still works.")
        finally:
            cap.release()
