from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List

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


manager = ConnectionManager()


size = 10
image = ["green" for i in range(size * size)]

print(image)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):    
    return templates.TemplateResponse("index.html", {"request": request, "image": image})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            index_str, color = data.split()
            index = int(index_str.replace('p', '')) - 1
            image[index] = color
            await manager.broadcast(f"{index_str} {color}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
