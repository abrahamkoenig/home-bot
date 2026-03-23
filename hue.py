#!/usr/bin/env python3
"""Philips Hue light control script — used by the Telegram bot and Apple Shortcuts."""
import urllib.request, json, sys, os

HUE_IP = os.environ.get("HUE_IP", "192.168.x.x")
API_KEY = os.environ.get("HUE_API_KEY", "your-hue-api-key")
STATE_FILE = os.path.expanduser("~/.hue_state.json")

def hue_request(endpoint, data=None):
    url = f"http://{HUE_IP}/api/{API_KEY}/{endpoint}"
    if data:
        req = urllib.request.Request(url, json.dumps(data).encode(), method="PUT")
    else:
        req = urllib.request.Request(url)
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())

def set_group(group_id, on, bri=None, ct=None):
    data = {"on": on}
    if bri is not None: data["bri"] = bri
    if ct is not None: data["ct"] = ct
    hue_request(f"groups/{group_id}/action", data)

def save_state():
    """Save current state of all lights before making changes."""
    r = urllib.request.urlopen(f"http://{HUE_IP}/api/{API_KEY}/lights", timeout=10)
    lights = json.loads(r.read().decode())
    state = {}
    for lid, l in lights.items():
        s = l.get("state", {})
        state[lid] = {"on": s.get("on"), "bri": s.get("bri"), "ct": s.get("ct")}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def restore_state():
    """Restore previously saved light state."""
    if not os.path.exists(STATE_FILE):
        print("No saved state found")
        return
    with open(STATE_FILE) as f:
        state = json.load(f)
    for lid, s in state.items():
        data = {"on": s["on"]}
        if s["on"] and s.get("bri") is not None:
            data["bri"] = s["bri"]
        if s["on"] and s.get("ct") is not None:
            data["ct"] = s["ct"]
        try:
            hue_request(f"lights/{lid}/state", data)
        except:
            pass

# --- Room configuration (customize to your setup) ---
# Map room names to Hue group IDs
ROOMS = {
    "wohnzimmer": [1, 10],
    "schlafzimmer": [19, 2],
    "kueche": [6],
    "buero": [13, 26],
    "kinderzimmer": [14],
    "garten": [24, 29, 34, 83],
    "bad": [8],
    "eingang": [5],
    "vorraum": [7],
    "treppenhaus": [20],
    "studio": [3],
    "keller": [12, 16],
    "ankleide": [9],
    "aussen": [32],
}
ALL_ROOMS = [g for groups in ROOMS.values() for g in groups]

cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

if cmd == "alles-aus":
    save_state()
    for g in ALL_ROOMS:
        set_group(g, False)
    print("All lights off")

elif cmd == "alles-an":
    for g in ALL_ROOMS:
        set_group(g, True, bri=254)
    print("All lights on")

elif cmd == "wiederherstellen":
    restore_state()

elif cmd == "gute-nacht":
    save_state()
    for g in ALL_ROOMS:
        set_group(g, False)
    set_group(2, True, bri=30, ct=450)
    print("Good night — nightlight on")

elif cmd == "guten-morgen":
    set_group(19, True, bri=200, ct=300)
    set_group(2, True, bri=200, ct=300)
    set_group(6, True, bri=254, ct=250)
    set_group(8, True, bri=254, ct=250)
    print("Good morning!")

elif cmd == "filmabend":
    save_state()
    set_group(1, False)
    set_group(10, True, bri=30, ct=450)
    print("Movie mode — living room dimmed")

elif cmd == "kochen":
    set_group(6, True, bri=254, ct=250)
    print("Kitchen bright")

elif cmd == "arbeiten":
    set_group(13, True, bri=254, ct=250)
    set_group(26, True, bri=128, ct=300)
    print("Office work light")

elif cmd == "garten-an":
    for g in ROOMS["garten"]:
        set_group(g, True, bri=254)
    print("Garden on")

elif cmd == "garten-aus":
    for g in ROOMS["garten"]:
        set_group(g, False)
    print("Garden off")

elif cmd == "entspannen":
    set_group(1, True, bri=128, ct=400)
    set_group(10, True, bri=100, ct=450)
    print("Relax — living room warm dimmed")

elif cmd == "status":
    r = urllib.request.urlopen(f"http://{HUE_IP}/api/{API_KEY}/groups", timeout=10)
    groups = json.loads(r.read().decode())
    for gid, g in sorted(groups.items(), key=lambda x: x[1].get("name", "")):
        if g.get("type") == "Room":
            on = "ON" if g.get("state", {}).get("any_on") else "off"
            print(f"  {g['name']:<25} {on}")
else:
    room = cmd.lower()
    action = sys.argv[2] if len(sys.argv) > 2 else "toggle"
    if room in ROOMS:
        for g in ROOMS[room]:
            if action == "an":
                set_group(g, True, bri=254)
            elif action == "aus":
                set_group(g, False)
            elif action == "toggle":
                r = hue_request(f"groups/{g}")
                is_on = r.get("state", {}).get("any_on", False)
                set_group(g, not is_on)
        print(f"{room.title()} {action}")
    else:
        print(f"Unknown: {cmd}")
        print(f"Commands: alles-aus, alles-an, wiederherstellen, gute-nacht, guten-morgen, filmabend, kochen, arbeiten, garten-an, garten-aus, entspannen, status")
        print(f"Rooms: {', '.join(ROOMS.keys())}")
