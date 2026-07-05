import cv2
import time
import os
import threading
from ultralytics import YOLO

# ===============================
# TELEGRAM IMPORT
# ===============================
try:
    import requests
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False


# ===============================
# SYSTEM SETTINGS
# ===============================
BUS_ID = "BUS-07"
MODE = "ACTIVE"  # ACTIVE or PASSIVE

ALERT_COOLDOWN = 15
CONF_THRESHOLD = 0.40
PASSIVE_PERSON_HOLD_TIME = 15

DANGEROUS_OBJECTS = ["knife", "scissors", "gun"]

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ===============================
# TELEGRAM FUNCTIONS
# ===============================
def send_telegram(message):
    if not TELEGRAM_ENABLED:
        print("Telegram disabled: requests is not installed.")
        return

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram is not configured.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print("Telegram alert sent successfully")
        else:
            print(f"Telegram failed: Status {response.status_code}")

    except Exception as e:
        print("Telegram network error:", e)


def send_telegram_async(message):
    thread = threading.Thread(
        target=send_telegram,
        args=(message,),
        daemon=True,
    )
    thread.start()


def build_alert_message(alerts, mode):
    unique_alerts = dict.fromkeys(alerts)

    return (
        "Bus Safety Alert\n"
        f"Bus ID: {BUS_ID}\n"
        f"Mode: {mode}\n"
        f"Detected: {', '.join(unique_alerts)}"
    )


def send_alert_if_needed(alerts, mode, current_time, last_alert_time):
    if not alerts:
        return last_alert_time

    if current_time - last_alert_time < ALERT_COOLDOWN:
        return last_alert_time

    message = build_alert_message(alerts, mode)
    send_telegram_async(message)

    return current_time


# ===============================
# DETECTION FUNCTIONS
# ===============================
def run_detection(model, frame):
    return model.track(
        frame,
        persist=True,
        tracker="custom_tracker.yaml",
        conf=CONF_THRESHOLD,
        verbose=False,
    )[0]


def draw_detection_box(frame, x1, y1, x2, y2, text, color):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    cv2.putText(
        frame,
        text,
        (x1, y1 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
    )


def handle_detection_label(label, track_id, mode):
    alerts = []
    person_detected = False
    color = (0, 255, 0)

    if mode == "ACTIVE":
        if label in DANGEROUS_OBJECTS:
            alerts.append(f"{label} (ID: {track_id})")
            color = (0, 0, 255)

    elif mode == "PASSIVE":
        if label == "person":
            person_detected = True
            color = (0, 0, 255)

        elif label in DANGEROUS_OBJECTS:
            alerts.append(f"{label} (ID: {track_id})")
            color = (0, 0, 255)

    return alerts, person_detected, color


def process_tracked_detections(results, frame, model, mode):
    alerts = []
    person_detected = False

    boxes = results.boxes.xyxy.cpu().numpy()
    clss = results.boxes.cls.cpu().numpy()
    confs = results.boxes.conf.cpu().numpy()
    ids = results.boxes.id.cpu().numpy().astype(int)

    for box, cls_id, conf, track_id in zip(boxes, clss, confs, ids):
        if conf < CONF_THRESHOLD:
            continue

        label = model.names[int(cls_id)]
        x1, y1, x2, y2 = map(int, box)

        new_alerts, detected_person, color = handle_detection_label(
            label,
            track_id,
            mode,
        )

        alerts.extend(new_alerts)

        if detected_person:
            person_detected = True

        text = f"ID: {track_id} {label} {conf:.2f}"
        draw_detection_box(frame, x1, y1, x2, y2, text, color)

    return alerts, person_detected


def process_raw_detections(results, frame, model, mode):
    alerts = []
    person_detected = False

    if results.boxes is None:
        return alerts, person_detected

    for box in results.boxes:
        conf = float(box.conf[0])

        if conf < CONF_THRESHOLD:
            continue

        cls_id = int(box.cls[0])
        label = model.names[cls_id]
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        new_alerts, detected_person, color = handle_detection_label(
            label,
            "No ID",
            mode,
        )

        alerts.extend(new_alerts)

        if detected_person:
            person_detected = True

        text = f"{label} {conf:.2f}"
        draw_detection_box(frame, x1, y1, x2, y2, text, color)

    return alerts, person_detected


def process_detections(results, frame, model, mode):
    if results.boxes is not None and results.boxes.id is not None:
        return process_tracked_detections(results, frame, model, mode)

    return process_raw_detections(results, frame, model, mode)


# ===============================
# PASSIVE MODE FUNCTIONS
# ===============================
def update_passive_mode(
    mode,
    person_detected,
    person_first_seen_time,
    current_time,
    alerts,
):
    if mode != "PASSIVE":
        return None

    if not person_detected:
        return None

    if person_first_seen_time is None:
        person_first_seen_time = current_time

    time_seen = current_time - person_first_seen_time

    if time_seen >= PASSIVE_PERSON_HOLD_TIME:
        alerts.append("Possible child/person left in bus")

    return person_first_seen_time


def draw_passive_timer(frame, mode, person_first_seen_time, current_time):
    if mode != "PASSIVE":
        return

    if person_first_seen_time is None:
        return

    time_seen = current_time - person_first_seen_time

    cv2.putText(
        frame,
        f"Person detected: {time_seen:.1f}s",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2,
    )


# ===============================
# UI FUNCTIONS
# ===============================
def draw_status(frame, mode, alerts):
    status_text = f"{mode} MODE: ALERT" if alerts else f"{mode} MODE: NORMAL"
    status_color = (0, 0, 255) if alerts else (0, 255, 0)

    cv2.putText(
        frame,
        status_text,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        status_color,
        2,
    )


def handle_keyboard(mode):
    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        return mode, True

    if key == ord("a"):
        return "ACTIVE", False

    if key == ord("p"):
        return "PASSIVE", False

    return mode, False


# ===============================
# SETUP FUNCTIONS
# ===============================
def setup_camera(camera_index=0):
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")

    return cap


def setup_model():
    return YOLO("yolov8n.pt")


# ===============================
# MAIN PROGRAM
# ===============================
def main():
    mode = MODE
    last_alert_time = 0
    person_first_seen_time = None

    model = setup_model()
    cap = setup_camera(0)

    print("Starting Bus Safety AI System...")

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                print("Failed to grab frame from camera.")
                break

            current_time = time.time()

            results = run_detection(model, frame)

            alerts, person_detected = process_detections(
                results,
                frame,
                model,
                mode,
            )

            person_first_seen_time = update_passive_mode(
                mode,
                person_detected,
                person_first_seen_time,
                current_time,
                alerts,
            )

            draw_passive_timer(
                frame,
                mode,
                person_first_seen_time,
                current_time,
            )

            last_alert_time = send_alert_if_needed(
                alerts,
                mode,
                current_time,
                last_alert_time,
            )

            draw_status(frame, mode, alerts)

            cv2.imshow("Bus Safety AI", frame)

            new_mode, should_quit = handle_keyboard(mode)

            if should_quit:
                break

            if new_mode != mode:
                mode = new_mode
                person_first_seen_time = None
                print(f"Switched to {mode} mode")

    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()