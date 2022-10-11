import asyncio
import datetime
import json
from threading import Thread

import websockets
from geographiclib.geodesic import Geodesic
from geopy import distance

from app import Strike


class WssClient(Thread):
    def __init__(self, url, chats):
        Thread.__init__(self)
        self.url = url
        self.chats = chats
        self.last_update = datetime.datetime.utcnow()
        self.count = 0
        self.message = None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.ws_loop())
        loop.close()

    async def ws_loop(self):
        async for websocket in websockets.connect(self.url):
            try:
                await websocket.send('{"a":767}')
                self.message = await websocket.recv()
                await self.process_wss()

            except websockets.ConnectionClosed:
                print("Connection closed")
                continue

    async def process_wss(self):
        if self.message:
            dec = self.prepare()
            j = json.loads(dec)
            for chat_id, chat in self.chats.chats.items():
                location = (chat.lat, chat.lon)
                try:
                    strike = Strike(lat=j['lat'], lon=j['lon'], timestamp=j['time'])
                    print(strike.timestamp)
                except Exception as e:
                    print(e)
                    return
                dist = round(Geodesic.WGS84.Inverse(*location, strike.lat, strike.lon)['s12']/1000, 2)
                if dist < chat.radius:
                    strike.set_address()
                    chat.increment_count()
                    chat.add_strike(strike)
                    print(chat.chat_id, 'strike ⚡')

    def prepare(self):
        b = self.message
        e = {}
        d = list(b)
        c = d[0]
        f = c
        g = [c]
        h = 256
        o = h
        for b in range(1, len(d)):
            a = ord(d[b][0])
            a = d[b] if h > a else (e[a] if (a in e) else f + c)
            g.append(a)
            c = a[0]
            e[o] = f + c
            o += 1
            f = a
        return "".join(g)
