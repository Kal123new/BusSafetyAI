import cv2
import time
from ultralytics import YOLO

# ===============================
# TELEGRAM IMPORT
# ===============================
try:
    from notify_telegram import send_telegram
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False

# ===============================
# SYSTEM SETTINGS
# ===============================
BUS_ID = "BUS-07"

MODE = "ACTIVE"   # ACTIVE or PASSIVE

ALERT_COOLDOWN = 30  # seconds
last_alert_time = 0

# Only objects we actually care about
DANGEROUS_OBJECTS = [
    "knife",
    "scissors",
    "gun"
]

# ===============================
# LOAD YOLOv8 MODEL
# ===============================
model = YOLO("yolov8n.pt")

# ===============================
# CAMERA SETUP
# ===============================
cap = cv2.VideoCapture(0)  # change to 0/1/2 if needed

# ===============================
# MAIN LOOP
# ===============================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    alerts = []  # reset every frame

    results = model(frame, verbose=False)[0]

    for box in results.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = model.names[cls_id]

        if conf < 0.15:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        color = (0, 255, 0)

        # ===============================
        # ACTIVE MODE LOGIC
        # ===============================
        if MODE == "ACTIVE":
            if label in DANGEROUS_OBJECTS:
                alerts.append(label)
                color = (0, 0, 255)

        # ===============================
        # PASSIVE MODE LOGIC
        
        elif MODE == "PASSIVE":
            if label == "person":
                alerts.append("person")
                color = (0, 0, 255)
            elif label in DANGEROUS_OBJECTS:
                alerts.append(label)
                color = (0, 0, 255)

        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f"{label} {conf:.2f}",
            (x1, y1 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2
        )


    # TELEGRAM ALERT LOGIC
    current_time = time.time()

    if alerts and TELEGRAM_ENABLED:
        if current_time - last_alert_time >= ALERT_COOLDOWN:
            message = (
                "🚨 Bus Safety Alert\n"
                f"Bus ID: {BUS_ID}\n"
                f"Mode: {MODE}\n"
                f"Detected: {', '.join(set(alerts))}"
            )
            send_telegram(message)
            last_alert_time = current_time

    # STATUS DISPLAY
    if alerts:
        status_text = f"{MODE} MODE: ALERT"
        status_color = (0, 0, 255)
    else:
        status_text = f"{MODE} MODE: NORMAL"
        status_color = (0, 255, 0)

    cv2.putText(
        frame,
        status_text,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        status_color,
        2
    )

    cv2.imshow("Bus Safety AI", frame)

    # KEYBOARD CONTROLS
    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break
    elif key == ord("a"):
        MODE = "ACTIVE"
    elif key == ord("p"):
        MODE = "PASSIVE"

# CLEANUP
cap.release()
cv2.destroyAllWindows()
