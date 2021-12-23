from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi import responses
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import datetime
import uuid


FIELD_SIZE = 50
CELL_SIZE = 8


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
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
            
    def get_online(self):
        return len(self.active_connections)


manager = ConnectionManager()

players = {}


size = FIELD_SIZE
image = ["white" for i in range(size * size)]


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
    await manager.broadcast(f"online {manager.get_online()}")
    try:
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
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"online {manager.get_online()}")
