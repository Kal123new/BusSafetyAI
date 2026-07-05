<img width="700" height="150" alt="image" src="https://github.com/user-attachments/assets/0cb4c2ff-039e-4482-a8dd-e24a0bb10988" />


An AI-powered computer vision system designed to prevent children from being left behind in school buses and to detect potential security threats in real-time.

✨ Features
Dual-Mode Operation:

Active Mode: Monitored while the bus is in transit. Focuses exclusively on safety hazards (Must manually turn on in code).

Passive Mode: Engaged after the route is completed. Scans for forgotten children (person detection) alongside threat objects.

Switch between modes by pressing A or P.

Cooldown Protection: Avoids spamming notifications by enforcing a configurable cooldown period (default: 30 seconds) between alerts.

🛠️ Tech Stack
Language: Python 3.8+

AI Model: Ultralytics YOLOv8 (Nano variant for edge-device efficiency)

Vision Engine: OpenCV

Notifications: python-telegram-bot API

📦 Installation & Setup
1. Clone the Repository

git clone https://github.com/yourusername/bus-safety-ai.git
cd bus-safety-ai

2. Install Dependencies
Ensure you have Python installed, then run:


pip install opencv-python ultralytics python-telegram-bot

3. Configure Telegram Integration
Create a bot using Telegram's BotFather to get your Bot Token.

Retrieve your Chat ID (or channel ID where alerts will be sent).

Update the credentials in your script file:

Python
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

CHAT_ID = YOUR_CHAT_ID_NUMERIC

https://github.com/user-attachments/assets/7e188455-11bd-40b4-adf6-9ae336b5dcc9

