import os


class TELEGRAM:
    API_KEY = os.environ["TELEGRAM_BOT_TOKEN"]


class DATABASE:
    DB_URL = os.environ["DATABASE_URL"]
