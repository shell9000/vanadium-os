#!/usr/bin/env python3
"""
Vanadium OS - Music Server WebUI + MPD Controller
整合硬盤管理介面同 MPD 播放控制
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import json
import psutil
import ipaddress
import mpd
from pathlib import Path
from typing import List, Dict, Any

app = FastAPI(title="Vanadium OS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MPD_HOST = "localhost"
MPD_PORT = 6600
FRONTEND = Path(__file__).parent.parent / "frontend"

def get_mpd():
    c = mpd.MPDClient()
    c.connect(MPD_HOST, MPD_PORT)
    return c

def run_command(cmd: List[str]) -> Dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Frontend Routes ──────────────────────────────────────────

@app.get("/")
async def root():
    f = FRONTEND / "vvai-player-local.html"
    return HTMLResponse(content=f.read_text()) if f.exists() else JSONResponse({"error": "Player not found"})

@app.get("/storage")
async def storage():
    f = FRONTEND / "storage.html"
    return HTMLResponse(content=f.read_text()) if f.exists() else JSONResponse({"error": "Storage UI not found"})

@app.get("/player-glass")
async def player_glass():
    f = FRONTEND / "liquid-glass-player.html"
    return HTMLResponse(content=f.read_text()) if f.exists() else HTTPException(404)

@app.get("/logo.jpg")
async def logo():
    p = FRONTEND / "vv-logo.jpg"
    return FileResponse(p) if p.exists() else HTTPException(404)

# ── MPD API ──────────────────────────────────────────────────

@app.get("/api/status")
async def mpd_status():
    try:
        c = get_mpd()
        status = c.status()
        song = c.currentsong()
        c.disconnect()
        return {
            "state": status.get("state", "stop"),
            "volume": int(status.get("volume", 50)),
            "elapsed": float(status.get("elapsed", 0)),
            "duration": float(status.get("duration", 0)),
            "repeat": status.get("repeat") == "1",
            "random": status.get("random") == "1",
            "title": song.get("title", song.get("file", "").split("/")[-1] if song.get("file") else ""),
            "artist": song.get("artist", ""),
            "album": song.get("album", ""),
            "file": song.get("file", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/play")
async def mpd_play():
    c = get_mpd(); c.play(); c.disconnect(); return {"ok": True}

@app.post("/api/pause")
async def mpd_pause():
    c = get_mpd(); c.pause(); c.disconnect(); return {"ok": True}

@app.post("/api/next")
async def mpd_next():
    c = get_mpd(); c.next(); c.disconnect(); return {"ok": True}

@app.post("/api/prev")
async def mpd_prev():
    c = get_mpd(); c.previous(); c.disconnect(); return {"ok": True}

@app.post("/api/stop")
async def mpd_stop():
    c = get_mpd(); c.stop(); c.disconnect(); return {"ok": True}

@app.post("/api/volume")
async def mpd_volume(data: dict):
    c = get_mpd()
    vol = max(0, min(100, int(data.get("volume", 50))))
    c.setvol(vol); c.disconnect()
    return {"ok": True, "volume": vol}

@app.post("/api/seek")
async def mpd_seek(data: dict):
    c = get_mpd()
    c.seekcur(float(data.get("position", 0))); c.disconnect()
    return {"ok": True}

@app.post("/api/repeat")
async def mpd_repeat():
    c = get_mpd()
    status = c.status()
    c.repeat(0 if status.get("repeat") == "1" else 1); c.disconnect()
    return {"ok": True}

@app.post("/api/random")
async def mpd_random():
    c = get_mpd()
    status = c.status()
    c.random(0 if status.get("random") == "1" else 1); c.disconnect()
    return {"ok": True}

@app.get("/api/library")
async def mpd_library(path: str = ""):
    c = get_mpd()
    items = c.lsinfo(path) if path else c.lsinfo()
    c.disconnect()
    return {"ok": True, "items": items}

@app.post("/api/search")
async def mpd_search(data: dict):
    c = get_mpd()
    results = c.search("any", data.get("query", ""))
    c.disconnect()
    return {"ok": True, "results": results[:50]}

@app.post("/api/play_file")
async def mpd_play_file(data: dict):
    c = get_mpd()
    c.clear(); c.add(data.get("file", "")); c.play(); c.disconnect()
    return {"ok": True}

@app.get("/api/queue")
async def mpd_queue():
    c = get_mpd()
    q = c.playlistinfo(); c.disconnect()
    return {"ok": True, "queue": q}

# ── Storage API ──────────────────────────────────────────────

@app.get("/api/disks")
async def get_disks():
    try:
        result = run_command(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL"])
        if result["success"]:
            return json.loads(result["stdout"])
        raise HTTPException(status_code=500, detail=result.get("stderr"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mounts")
async def get_mounts():
    try:
        partitions = psutil.disk_partitions(all=True)
        mounts = []
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                mounts.append({"device": p.device, "mountpoint": p.mountpoint, "fstype": p.fstype,
                                "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.percent})
            except:
                mounts.append({"device": p.device, "mountpoint": p.mountpoint, "fstype": p.fstype})
        return {"mounts": mounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/mount")
async def mount_disk(data: dict):
    device = data.get("device")
    mountpoint = data.get("mountpoint")
    fstype = data.get("fstype", "auto")
    if not device or not mountpoint:
        raise HTTPException(status_code=400, detail="Missing device or mountpoint")
    run_command(["mkdir", "-p", mountpoint])
    result = run_command(["mount", "-t", fstype, device, mountpoint])
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("stderr"))
    return {"success": True}

@app.post("/api/umount")
async def umount_disk(data: dict):
    mountpoint = data.get("mountpoint")
    result = run_command(["umount", mountpoint])
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("stderr"))
    return {"success": True}

@app.get("/api/system")
async def system_status():
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        roon = run_command(["systemctl", "is-active", "roonserver"])["stdout"].strip()
        return {"cpu_percent": cpu, "memory_total": mem.total, "memory_used": mem.used,
                "memory_percent": mem.percent, "roon_status": roon}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fstab/add")
async def add_fstab(data: dict):
    device = data.get("device")
    mountpoint = data.get("mountpoint")
    fstype = data.get("fstype", "auto")
    options = data.get("options", "defaults")
    if not device or not mountpoint:
        raise HTTPException(status_code=400, detail="Missing device or mountpoint")
    fstab = Path("/etc/fstab")
    content = fstab.read_text()
    if device in content:
        raise HTTPException(status_code=400, detail="Already in fstab")
    fstab.write_text(content + f"\n{device} {mountpoint} {fstype} {options} 0 2\n")
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
