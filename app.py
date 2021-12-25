from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.staticfiles import StaticFiles
from fastapi import responses
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import random
import datetime
import uuid
import aioredis
from os import environ
import psycopg2

DB_URL = environ.get("DATABASE_URL")
create_table_sql = '''create table IF NOT EXISTS logs (log_str text);'''
insert_log_str = '''INSERT INTO logs (log_str) VALUES (%s)'''
conn = psycopg2.connect(DB_URL)
with conn:
    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        conn.commit()

R = aioredis.from_url(environ.get("REDISTOGO_URL"))

FIELD_SIZE = 50
CELL_SIZE = 8
LOG_SIZE = 100

with open('wishes.txt', 'rt', encoding='utf-8') as f:
    wishes = f.read()
wishes = wishes.split('\n')

def get_random_wish(wishes):
    return random.choice(wishes)

def cooldown(player_id, players, timeout=datetime.timedelta(seconds=3)):
    timestamp = players[player_id]
    timedelta = datetime.datetime.now() - timestamp 
    if timedelta < timeout:
        return True, timeout - timedelta 
    else: 
        return False, timeout - timedelta
     

app = FastAPI()
templates = Jinja2Templates(directory="templates")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        if websocket.client_state.CONNECTED:
            try:
                await websocket.send_text(message)
            except:
                pass
            
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            if connection.client_state.CONNECTED:
                try:
                    await connection.send_text(message)
                except:
                    pass
            elif connection.client_state.DISCONNECTED:
                self.disconnect(connection)

            
    def get_online(self):
        return len(self.active_connections)


manager = ConnectionManager()

players = {}

size = FIELD_SIZE
image = ["white" for i in range(size * size)]

pixels = {str(i): color for i, color in enumerate(image)}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    player_id = request.cookies.get('player_id')
    if not player_id:
        player_id = str(uuid.uuid4())
        players[player_id] = datetime.datetime.now()
    if player_id not in players:
        player_id = str(uuid.uuid4())
        players[player_id] = datetime.datetime.now()
    
    response = templates.TemplateResponse("index.html", {"request": request, "image": image, "field_size": FIELD_SIZE, "cell_size": CELL_SIZE, "online": manager.get_online()})
    response.set_cookie(key='player_id', value=player_id)
    return response

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await manager.broadcast(f"online {manager.get_online()}")
        while True:
            data = await websocket.receive_text()
           # print(data, websocket)
            index_str, color, player_id = data.split()
            index = int(index_str.replace('p', '')) - 1       
            is_cooldown, timedelta = cooldown(player_id, players)
            if is_cooldown:
                msg = f"cooldown {timedelta.total_seconds()}"
                await manager.send_personal_message(msg, websocket)
            else:
                image[index] = color
                players[player_id] = datetime.datetime.now()
                await manager.broadcast(f"{index_str} {color}")
                
                # save to redis and log DB
                log_string = f'{index} {color} {player_id} {datetime.datetime.now().isoformat()}'
                log_len = 0
                try:
                    await R.rpush("log", log_string)
                    log_len = await R.llen("log")
                    if log_len > LOG_SIZE:
                        log_rows = [await R.lpop("log") for i in range(LOG_SIZE)]
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute(insert_log_str, (str(log_rows),))
                                conn.commit()
                except:
                    print("cant push to redis")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        try:
            await manager.broadcast(f"online {manager.get_online()}")
        except:
            pass


@app.get("/wish", response_class=HTMLResponse)
def wish(request: Request):
    return templates.TemplateResponse("wish.html", {"request": request, "wish": get_random_wish(wishes)})
    
