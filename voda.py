# server.py
import socket
import threading
import json
import random
from datetime import datetime
from pathlib import Path

HOST = "0.0.0.0"
PORT = 4443

DB_DIR = Path("~/Desktop/ChatLocalDB").expanduser()
DB_DIR.mkdir(exist_ok=True)
USERS_FILE = DB_DIR / "users.json"
MESSAGES_FILE = DB_DIR / "messages.json"
ONLINE = {}

def init():
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}")
    if not MESSAGES_FILE.exists():
        MESSAGES_FILE.write_text("[]")

def load_users(): return json.loads(USERS_FILE.read_text())
def save_users(u): USERS_FILE.write_text(json.dumps(u, indent=2))
def load_msgs(): return json.loads(MESSAGES_FILE.read_text())
def save_msgs(m): MESSAGES_FILE.write_text(json.dumps(m, indent=2))

def gen_id():
    while True:
        uid = str(random.randint(1000000000, 9999999999))
        if uid not in load_users():
            return uid

def broadcast_online():
    ids = [info["id"] for info in ONLINE.values()]
    payload = json.dumps({"type": "online_list", "online": ids}).encode() + b"\n"
    for c in list(ONLINE.keys()):
        try: c.send(payload)
        except: pass

def handle(client, addr):
    print(f"[+] {addr} connecté")
    buffer = ""
    try:
        while True:
            data = client.recv(4096).decode('utf-8')
            if not data: break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line: continue
                msg = json.loads(line)
                typ = msg.get("type")
                if typ == "register":
                    name = (msg.get("name") or "").strip()
                    surname = (msg.get("surname") or "").strip()
                    display = f"{name} {surname}".strip() or name
                    uid = gen_id()
                    users = load_users()
                    users[uid] = {"name": display, "photo": "", "created_at": datetime.now().isoformat()}
                    save_users(users)
                    ONLINE[client] = {"id": uid, "name": display}
                    client.send(json.dumps({"type": "registered", "user_id": uid, "name": display}).encode() + b"\n")
                    broadcast_online()
                elif typ == "login":
                    uid = msg["user_id"]
                    users = load_users()
                    if uid in users:
                        ONLINE[client] = {"id": uid, "name": users[uid]["name"]}
                        client.send(json.dumps({"type": "login_success", "user": users[uid], "user_id": uid}).encode() + b"\n")
                        broadcast_online()
                elif typ == "search_user":
                    uid = msg["user_id"]
                    users = load_users()
                    if uid in users:
                        client.send(json.dumps({"type": "user_found", "user": users[uid], "user_id": uid}).encode() + b"\n")
                    else:
                        client.send(json.dumps({"type": "user_not_found"}).encode() + b"\n")
                elif typ == "send_message":
                    sender = ONLINE[client]["id"]
                    to = msg["to"]
                    text = msg["message"]
                    msgs = load_msgs()
                    m = {"id": len(msgs)+1, "from": sender, "to": to, "message": text, "timestamp": datetime.now().isoformat()}
                    msgs.append(m)
                    save_msgs(msgs)
                    payload = json.dumps({"type": "new_message", "message": m}).encode() + b"\n"
                    for c, info in list(ONLINE.items()):
                        if info["id"] in (sender, to):
                            try: c.send(payload)
                            except: pass
                elif typ == "get_messages":
                    uid = ONLINE[client]["id"]
                    with_id = msg["with"]
                    all_msgs = load_msgs()
                    convo = [m for m in all_msgs if (m["from"] == uid and m["to"] == with_id) or (m["from"] == with_id and m["to"] == uid)]
                    client.send(json.dumps({"type": "messages_history", "messages": convo}).encode() + b"\n")
    except Exception as e:
        print(f"Erreur {addr}: {e}")
    finally:
        if client in ONLINE:
            del ONLINE[client]
        client.close()
        broadcast_online()
        print(f"[-] {addr} déconnecté")

def start():
    init()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(10)
    print(f"Serveur lancé sur 0.0.0.0:{PORT}")
    print("En attente de connexions...")
    while True:
        c, a = s.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    start()
