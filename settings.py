import os


class TELEGRAM:
    API_KEY = os.environ["TELEGRAM_BOT_TOKEN"]


class DATABASE:
    __uri = os.environ["DATABASE_URL"]
    DB_URL = __uri.replace("postgres://", "postgresql://", 1) if __uri.startswith("postgres://") else __uri

