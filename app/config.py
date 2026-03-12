import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'madden.db')}"

DATA_DIR = os.path.join(BASE_DIR, "data")

APP_TITLE = "Madden 26 Franchise Tracker"

HOST = "0.0.0.0"
PORT = 5000
