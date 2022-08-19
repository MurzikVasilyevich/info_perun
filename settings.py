import os


class TELEGRAM:
    API_KEY = os.environ["TELEGRAM_BOT_TOKEN"]


class DATABASE:
    __uri = os.environ["DATABASE_URL"]
    DB_URL = __uri.replace("postgres://", "postgresql://", 1) if __uri.startswith("postgres://") else __uri


class WEBSOCKET:
    URL = os.environ["WEBSOCKET_URL"]


class DEFAULTS:
    TIMESPAN = 60
    RADIUS = 100


class OPTIONS:
    DISTANCES = [5, 10, 50, 100]
    TIMESPANS = [0.5, 1, 2, 5]


class UOM:
    DISTANCE = "км"
    TIME = "хв"
