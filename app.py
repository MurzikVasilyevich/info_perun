import datetime
import os
import re
import time

import numpy as np
from geographiclib.geodesic import Geodesic
from geopy.geocoders import Nominatim

import matplotlib
import matplotlib.pyplot as plt

import pytz
import telebot
from telebot import types
from sqlalchemy import Column, Integer, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from timezonefinder import TimezoneFinder
from threading import Thread

import settings as s
import wssclient

matplotlib.use('Agg')
engine = create_engine(s.DATABASE.DB_URL, echo=True)
Base = declarative_base()

"""
start - Розпочати
info - Переглянути поточні налаштування
location - Задати локацію
radius - Задати зону охоплення
refresh - Задати частоту оновлення
map - Переглянути карту
help - Про бота
"""


class ChatLocal:
    def __init__(self, chat_id, lat, lon, timespan=s.DEFAULTS.TIMESPAN, radius=s.DEFAULTS.RADIUS,
                 count=0, last_update=datetime.datetime.utcnow()):
        self.chat_id = chat_id
        self.lat = lat
        self.lon = lon
        self.timespan = timespan
        self.radius = radius
        self.strikes = []
        self.count = len(self.strikes)
        self.last_update = last_update
        self.thetas = []
        self.rs = []

    def increment_count(self):
        self.count += 1

    def reset_count(self):
        self.count = 0
        self.last_update = datetime.datetime.utcnow()
        self.strikes = []
        self.thetas = []
        self.rs = []

    def add_strike(self, strike):
        bearing = get_bearing(self.lat, self.lon, strike.lat, strike.lon)
        bearing['time'] = strike.timestamp
        self.strikes.append(bearing)
        self.thetas.append(bearing['theta'])
        self.rs.append(round(bearing['r'] / 1000))


def get_bearing(lat1, lon1, lat2, lon2):
    inverse = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
    loc = {'theta': inverse['azi1'], 'r': inverse['s12']}
    return loc


class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    lat = Column(Float)
    lon = Column(Float)
    timespan = Column(Float)
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


class Address:
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon
        self.municipality = None
        self.district = None
        self.state = None
        self.country = None
        self.country_code = None
        self.get_address()

    def __str__(self):
        return f'{self.lat},{self.lon}'

    def __repr__(self):
        return f'{self.lat},{self.lon}'

    def get_address(self):
        geolocator = Nominatim(user_agent="PerunInfo")
        location = geolocator.reverse(f'{self.lat},{self.lon}', exactly_one=True)
        if location is None:
            print(f"No location found for {self.lat}/{self.lon}")
            return
        address = location.raw['address']
        self.country_code = address['country_code'] if 'country_code' in address else None
        if self.country_code in s.OPTIONS.COUNTRIES:
            self.municipality = address['municipality'] if 'municipality' in address else None
            self.district = address['district'] if 'district' in address else None
            self.state = address['state'] if 'state' in address else None
            self.country = address['country'] if 'country' in address else None


class Strike:
    def __init__(self, lat, lon, timestamp):
        self.lat = lat
        self.lon = lon
        self.timestamp = timestamp
        self.address = None

    def set_address(self):
        self.address = Address(self.lat, self.lon)


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
Session.configure(bind=engine)


def utc_to_local(utc_dt, lat, lng):
    timezone = TimezoneFinder().timezone_at(lng=lng, lat=lat)
    utc_time = datetime.datetime.utcnow()
    return utc_dt + pytz.timezone(timezone).localize(utc_time).utcoffset()


class TelegramPollingThread(Thread):
    def __init__(self, chats):
        Thread.__init__(self)
        self.chats = chats
        self.bot = telebot.TeleBot(s.TELEGRAM.API_KEY)

        @self.bot.message_handler(commands=['info'])
        def info(message):
            session = Session()
            chat_id = message.chat.id
            chat = session.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat is None:
                self.bot.send_message(chat_id, 'Вы не зареєстровані у боті')
                return
            self.bot.send_message(chat_id,
                                  f"Ви отримуєте інформацію про кількість блискавок у радіусі {str(chat.radius)}км від наступної "
                                  f"точки кожні {str(chat.timespan)} секунд")
            self.bot.send_location(chat_id, chat.lat, chat.lon, horizontal_accuracy=chat.radius * 1000)
            session.close()

        @self.bot.message_handler(commands=['map'])
        def send_map(message):
            session = Session()
            chat_id = message.chat.id
            chat = session.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat is None:
                self.bot.send_message(chat_id, 'Вы не зареєстровані у боті')
                return
            self.bot.send_message(chat_id,
                                  text=f"<a href='https://map.blitzortung.org/#10/{chat.lat}/{chat.lon}'>🗺</a>",
                                  parse_mode="HTML")
            session.close()

        @self.bot.message_handler(commands=['start'])
        def add_user(message):
            session = Session()
            chat_id = message.chat.id
            if session.query(Chat).filter(Chat.chat_id == chat_id).count() == 0:
                session.add(Chat(chat_id=chat_id, lat=0, lon=0, timespan=s.DEFAULTS.TIMESPAN, radius=s.DEFAULTS.RADIUS))
                session.commit()
                session.close()
                self.chats.get_from_base()
                self.bot.send_message(chat_id=chat_id, text='Вас додано до користувачів')
            print(chat_id)
            self.request_location(chat_id, message)

        @self.bot.message_handler(commands=['location'])
        def set_location(message):
            chat_id = message.chat.id
            print(chat_id)
            self.request_location(chat_id, message)

        @self.bot.message_handler(commands=['radius'])
        def set_radius(message):
            chat_id = message.chat.id
            print(chat_id)
            self.bot.send_message(message.chat.id, 'Встановіть радіус охоплення')
            keyboard = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
            for i in s.OPTIONS.DISTANCES:
                button = types.KeyboardButton(text=str(i) + s.UOM.DISTANCE)
                keyboard.add(button)
            self.bot.send_message(message.chat.id, "Виберіть радіус відстані", reply_markup=keyboard)

        @self.bot.message_handler(commands=['refresh'])
        def set_timespan(message):
            chat_id = message.chat.id
            print(chat_id)
            self.bot.send_message(message.chat.id, 'Виберіть проміжок часу оновлення')
            keyboard = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
            for i in s.OPTIONS.TIMESPANS:
                button = types.KeyboardButton(text=str(i) + s.UOM.TIME)
                keyboard.add(button)
            self.bot.send_message(message.chat.id, "Виберіть проміжок часу", reply_markup=keyboard)

        @self.bot.message_handler(commands=['help'])
        def send_help(message):
            self.bot.send_message(message.chat.id, "Цей чатбот дозволяє вам отримувати положення близьких блискавок.")

        @self.bot.message_handler(content_types=['text'])
        def send_text(message):
            session = Session()
            chat = session.query(Chat).filter(Chat.chat_id == message.chat.id).first()

            dist_message = re.search(r'^(?P<value>[0-9]+)' + s.UOM.DISTANCE + '$', message.text)
            time_message = re.search(r'^(?P<value>([0-9]*[.])?[0-9]+)' + s.UOM.TIME + '$', message.text)

            if dist_message:
                chat.radius = int(dist_message.group('value'))
                self.bot.send_message(message.chat.id, f"Вибрано радіус відстані {chat.radius}км",
                                      reply_markup=types.ReplyKeyboardRemove())

            if time_message:
                t = float(time_message.group(1))
                chat.timespan = round(t * 60)
                self.bot.send_message(message.chat.id, f"Вибрано оновлення кожні {t} хвилин",
                                      reply_markup=types.ReplyKeyboardRemove())
            session.commit()
            self.chats.get_from_base()
            session.close()

        @self.bot.message_handler(content_types=['location'])
        def add_location(message):
            session = Session()
            chat = session.query(Chat).filter(Chat.chat_id == message.chat.id).first()
            lat = message.location.latitude
            lon = message.location.longitude
            print(lat, lon)
            chat.lat = lat
            chat.lon = lon
            session.commit()
            self.chats.get_from_base()
            self.bot.send_message(message.chat.id, 'Локація встановлена', reply_markup=types.ReplyKeyboardRemove())
            session.close()

    def run(self):
        self.bot.infinity_polling()

    def request_location(self, chat_id, message):
        self.bot.send_message(message.chat.id,
                              'Встановіть локацію за допомогою повідомлення "Поділитись локацією", або відправте '
                              'своє розташування як повідомлення')
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        button_geo = types.KeyboardButton(text='Поділитись локацією', request_location=True)
        keyboard.add(button_geo)
        self.bot.send_message(chat_id, 'Ви можете вибрати локацію за допомогою кнопки "Поділитись локацією"',
                              reply_markup=keyboard)


def plot_polar(chat):
    plt.polar([np.radians(t) for t in chat.thetas], chat.rs, marker="$\u26a1$", markersize=30,
              markerfacecolor="yellow", markeredgecolor="red", markeredgewidth=1)
    ax = plt.subplot(111, polar=True)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_xticks([np.radians(i) for i in range(0, 360, 45)])
    ax.set_xticklabels(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'])
    image = f'windrose{chat.chat_id}.png'
    plt.savefig(image, bbox_inches='tight')
    plt.clf()
    return image


def chat_message(chat):
    start = utc_to_local(chat.last_update, chat.lat, chat.lon)
    stop = utc_to_local(chat.last_update + datetime.timedelta(seconds=chat.timespan), chat.lat,
                        chat.lon)
    time_format = '%H:%M:%S' if chat.timespan < 60 else '%H:%M'
    timestamp = f"{start.strftime(time_format)}-{stop.strftime(time_format)}"
    text = f"{'⚡' * chat.count}\n{timestamp}"
    return text


class TelegramPostingThread(Thread):
    def __init__(self, chats):
        Thread.__init__(self)
        self.chats = chats
        self.bot = telebot.TeleBot(s.TELEGRAM.API_KEY)

    def run(self):
        while True:
            self.send_updates()
            self.chats.get_from_base()
            time.sleep(5)

    def send_updates(self):
        for chat_id, chat in self.chats.chats.items():
            print(chat.timespan)
            if datetime.datetime.utcnow() > chat.last_update + datetime.timedelta(seconds=chat.timespan):
                print(f"{chat.chat_id}: {chat.lat}/{chat.lon} {chat.count} - {chat.last_update}")
                if chat.count > 0:
                    # image = plot_polar(chat)
                    text = chat_message(chat)
                    try:
                        self.bot.send_message(chat.chat_id, text, parse_mode="HTML")
                        # self.bot.send_photo(chat.chat_id, open(image, 'rb'))
                        # os.remove(image)
                    except Exception as e:
                        print(e)
                        pass
                    chat.reset_count()
                else:
                    chat.reset_count()
            else:
                print(chat.chat_id, 'not time')


def main():
    chats = Chats()
    tg_thread = TelegramPollingThread(chats=chats)
    tg_thread.start()
    tg_summary_thread = TelegramPostingThread(chats=chats)
    tg_summary_thread.start()
    client = wssclient.WssClient(url=s.WEBSOCKET.URL, chats=chats)
    client.start()


if __name__ == '__main__':
    main()
    while True:
        time.sleep(1)
