import datetime
import json
import re
import threading
import time

import telebot
import websocket
from geopy import distance
from sqlalchemy import Column, Integer, Float
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from telebot import types

import settings as s

engine = create_engine('sqlite:///blitz.db?check_same_thread=False', echo=True)
Base = declarative_base()


class ChatLocal:
    def __init__(self, chat_id, lat, lon, timespan=60, radius=100, count=0, last_update=datetime.datetime.now()):
        self.chat_id = chat_id
        self.lat = lat
        self.lon = lon
        self.timespan = timespan
        self.radius = radius
        self.count = count
        self.last_update = last_update

    def increment_count(self):
        self.count += 1

    def reset_count(self):
        self.count = 0
        self.last_update = datetime.datetime.now()


class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    lat = Column(Float)
    lon = Column(Float)
    timespan = Column(Integer)
    radius = Column(Integer)

    def chat(self):
        chat = ChatLocal(chat_id=self.chat_id, lat=self.lat, lon=self.lon, timespan=self.timespan, radius=self.radius)
        return chat


class Chats:
    def __init__(self):
        self.chats = {}
        self.get_from_base()

    def add(self, chat_id, chat):
        self.chats[chat_id] = chat.chat()

    def get_from_base(self):
        session = Session()
        chats_base = session.query(Chat).all()
        session.close()
        for chat in chats_base:
            if chat.chat_id not in self.chats:
                self.add(chat.chat_id, chat)
            else:
                self.chats[chat.chat_id].lat = chat.lat
                self.chats[chat.chat_id].lon = chat.lon
                self.chats[chat.chat_id].timespan = chat.timespan
                self.chats[chat.chat_id].radius = chat.radius


class Strike:
    def __init__(self, lat, lon, time_stamp):
        self.lat = lat
        self.lon = lon
        self.time = time_stamp


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
Session.configure(bind=engine)
chats = Chats()


def on_message(ws, message):
    dec = prepare(message)
    j = json.loads(dec)
    strike = (j['lat'], j['lon'])
    for chat_id, chat in chats.chats.items():
        location = (chat.lat, chat.lon)
        if distance.distance(location, strike).km < chat.radius:
            chat.increment_count()
            print(chat.chat_id, 'strike')


def on_open(ws):
    ws.send('{"a":767}')


def prepare(b):
    a = None
    e = {}
    d = b
    c = d[0]
    f = c
    g = [c]
    h = 256
    o = h
    for b in range(1, len(d)):
        a = ord(d[b][0])
        a = d[b] if h > a else (e[a] if e[a] else f + c)
        g.append(a)
        c = a[0]
        e[o] = f + c
        o += 1
        f = a
    return "".join(g)


def ws_loop():
    ws = websocket.WebSocketApp("wss://ws8.blitzortung.org/",
                                on_message=on_message,
                                on_open=on_open)
    ws.run_forever()


key = s.TELEGRAM.API_KEY
bot = telebot.TeleBot(key, parse_mode=None)


@bot.message_handler(commands=['info'])
def info(message):
    session = Session()
    chat_id = message.chat.id
    chat = session.query(Chat).filter(Chat.chat_id == chat_id).first()
    if chat is None:
        bot.send_message(chat_id, 'Вы не зарегистрированы в боте')
        return
    bot.send_message(chat_id,
                     f"Ви отримуєте інформацію про кількість блискавок у радіусі {str(chat.radius)}км від наступної точки кожні {str(chat.timespan)} секунд")
    bot.send_location(chat_id, chat.lat, chat.lon, horizontal_accuracy=chat.radius * 1000)
    session.close()


@bot.message_handler(commands=['start'])
def add_user(message):
    session = Session()
    chat_id = message.chat.id
    if session.query(Chat).filter(Chat.chat_id == chat_id).count() == 0:
        session.add(Chat(chat_id=chat_id, lat=0, lon=0, timespan=60, radius=100))
        session.commit()
        chats.get_from_base()
        bot.send_message(chat_id=chat_id, text='Вас додано до користувачів')
    print(chat_id)
    bot.send_message(message.chat.id, 'Задайте, будь ласка локацію, за допомогою повідомлення "Поділитись локацією"')
    session.close()


@bot.message_handler(commands=['location'])
def set_location(message):
    chat_id = message.chat.id
    print(chat_id)
    bot.send_message(message.chat.id, 'Задайте, будь ласка локацію, за допомогою повідомлення "Поділитись локацією"')


@bot.message_handler(commands=['radius'])
def set_radius(message):
    chat_id = message.chat.id
    print(chat_id)
    bot.send_message(message.chat.id, 'Задайте, будь ласка радіус відстані, за допомогою клавіатури')
    keyboard = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
    button_1 = types.KeyboardButton(text="5км")
    button_2 = types.KeyboardButton(text="10км")
    button_3 = types.KeyboardButton(text="50км")
    button_4 = types.KeyboardButton(text="100км")
    keyboard.add(button_1, button_2, button_3, button_4)
    bot.send_message(message.chat.id, "Виберіть радіус відстані", reply_markup=keyboard)


@bot.message_handler(commands=['refresh'])
def set_timespan(message):
    chat_id = message.chat.id
    print(chat_id)
    bot.send_message(message.chat.id, 'Задайте, будь ласка проміжок часу, за допомогою клавіатури')
    keyboard = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
    button_1 = types.KeyboardButton(text="10сек")
    button_2 = types.KeyboardButton(text="30сек")
    button_3 = types.KeyboardButton(text="1хв")
    button_4 = types.KeyboardButton(text="5хв")
    keyboard.add(button_1, button_2, button_3, button_4)
    bot.send_message(message.chat.id, "Виберіть проміжок часу", reply_markup=keyboard)


@bot.message_handler(content_types=['text'])
def send_text(message):
    session = Session()
    chat = session.query(Chat).filter(Chat.chat_id == message.chat.id).first()
    pattern = re.compile("^(\d)+км$")

    if pattern.match(message.text):
        chat.radius = int(message.text[:-2])
        session.commit()
        chats.get_from_base()
        bot.send_message(message.chat.id, f"Вибрано радіус відстані {chat.radius}км")
        return

    pattern = re.compile("^(\d)+сек$")
    if pattern.match(message.text):
        chat.timespan = int(message.text[:-3])
        session.commit()
        chats.get_from_base()
        bot.send_message(message.chat.id, f"Вибрано оновлення кожні {chat.timespan} секунд")
        return

    pattern = re.compile("^(\d)+хв$")
    if pattern.match(message.text):
        chat.timespan = int(message.text[:-2]) * 60
        session.commit()
        chats.get_from_base()
        bot.send_message(message.chat.id, f"Вибрано оновлення кожні {chat.timespan} хвилин")
        return

    session.close()


@bot.message_handler(content_types=['location'])
def add_location(message):
    session = Session()
    chat = session.query(Chat).filter(Chat.chat_id == message.chat.id).first()
    lat = message.location.latitude
    lon = message.location.longitude
    print(lat, lon)
    chat.lat = lat
    chat.lon = lon
    session.commit()
    chats.get_from_base()
    bot.send_message(message.chat.id, 'Локація встановлена')
    session.close()


@bot.message_handler(commands=['help'])
def send_welcome(message):
    chat_id = message.chat.id
    print(chat_id)
    bot.reply_to(message, "Цей чатбот дозволяє вам отримувати положення близьких блискавок.")


def tg_summary():
    while True:
        time.sleep(5)
        for chat_id, chat in chats.chats.items():
            if datetime.datetime.now() > chat.last_update + datetime.timedelta(seconds=chat.timespan):
                print(f"{chat.chat_id}: {chat.lon}/{chat.lat} {chat.count} - {chat.last_update}")
                if chat.count > 0:
                    bot.send_message(chat.chat_id, '⚡' * chat.count)
                    chat.reset_count()
                else:
                    chat.reset_count()
            else:
                print(chat.chat_id, 'not time')
        chats.get_from_base()


def main():
    tg_thread = threading.Thread(target=bot.infinity_polling)
    ws_thread = threading.Thread(target=ws_loop)
    tg_summary_thread = threading.Thread(target=tg_summary)
    tg_thread.start()
    ws_thread.start()
    tg_summary_thread.start()


if __name__ == '__main__':
    main()
    while True:
        time.sleep(1)
