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
MUSIC_DIR = Path("/root/music")
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

AUDIO_EXTS = {'.wav','.flac','.mp3','.aac','.ogg','.dsf','.dff','.aif','.aiff','.m4a','.opus','.wv','.ape'}

@app.get("/api/library")
async def mpd_library(path: str = ""):
    import os, logging
    AUDIO_EXTS = {'.wav','.flac','.mp3','.aac','.ogg','.dsf','.dff','.aif','.aiff','.m4a','.opus','.wv','.ape'}
    SKIP_DIRS = {'artwork','scans','covers','booklet','bonus','extras','资源--索引'}
    base = Path(MUSIC_DIR) / path if path else Path(MUSIC_DIR)
    if not base.exists():
        return {"ok": False, "items": [], "error": f"Path not found: {path}"}
    items = []
    for entry in sorted(os.scandir(base), key=lambda e: e.name.lower()):
        if entry.name.startswith('.'): continue
        if entry.is_dir():
            if entry.name.lower() in SKIP_DIRS: continue
            rel = (path + '/' + entry.name) if path else entry.name
            # Check dir has audio files (recursively, max depth 2)
            import os as _os
            def has_audio(p, depth=0):
                if depth > 2: return False
                try:
                    for e in _os.scandir(p):
                        if e.is_file() and Path(e.name).suffix.lower() in AUDIO_EXTS:
                            return True
                        if e.is_dir() and depth < 2 and has_audio(e.path, depth+1):
                            return True
                except: pass
                return False
            if not has_audio(entry.path):
                continue
            items.append({'directory': rel})
        elif Path(entry.name).suffix.lower() in AUDIO_EXTS:
            rel = (path + '/' + entry.name) if path else entry.name
            items.append({'file': rel, 'title': Path(entry.name).stem})
    # Enrich with MPD tags if we have files
    if any('file' in i for i in items):
        try:
            c = get_mpd()
            mpd_items = c.lsinfo(path) if path else c.lsinfo()
            c.disconnect()
            mpd_map = {i['file']: i for i in mpd_items if 'file' in i}
            for i in items:
                if 'file' in i and i['file'] in mpd_map:
                    i.update(mpd_map[i['file']])
        except Exception as e:
            logging.warning(f'MPD enrich failed: {e}')
    # If root level: auto-expand dirs that contain only subdirs (collections like 劉漢盛)
    if not path:
        expanded = []
        for item in items:
            if 'directory' not in item:
                expanded.append(item)
                continue
            # check if this dir contains subdirs or files
            subbase = Path(MUSIC_DIR) / item['directory']
            try:
                subentries = list(os.scandir(subbase))
                sub_has_audio = any(
                    Path(e.name).suffix.lower() in AUDIO_EXTS
                    for e in subentries if not e.is_dir()
                )
                sub_dirs = [e for e in subentries if e.is_dir() and not e.name.startswith('.') and e.name.lower() not in SKIP_DIRS]
                if sub_dirs and not sub_has_audio:
                    # Collection folder - expand subdirs
                    for sd in sorted(sub_dirs, key=lambda e: e.name.lower()):
                        rel = item['directory'] + '/' + sd.name
                        expanded.append({'directory': rel})
                else:
                    expanded.append(item)
            except Exception:
                expanded.append(item)
        items = expanded
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
    
@app.get("/api/cover")
async def cover(path: str = ""):
    import os
    music_dir = MUSIC_DIR
    # Try image files in directory
    search_dirs = [music_dir / path]
    # if path is a file, search its parent dir too
    if path and not (music_dir / path).is_dir():
        search_dirs.append((music_dir / path).parent)
    import os
    for d in search_dirs:
        # Try standard names first
        for name in ["cover.jpg", "folder.jpg", "front.jpg", "Cover.jpg", "Folder.jpg", "COVER.jpg", "cover.png", "folder.png", "Front.jpg"]:
            p = d / name
            if p.exists():
                return FileResponse(str(p), media_type="image/jpeg")
        # Try any jpg/png in directory
        if d.is_dir():
            for fname in sorted(os.listdir(d)):
                if fname.startswith('.'): continue
                if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    p = d / fname
                    if p.exists():
                        return FileResponse(str(p), media_type="image/jpeg")
    # Try embedded cover via mutagen
    try:
        target = music_dir / path
        audio_file = None
        if target.is_dir():
            for f in sorted(os.listdir(target)):
                if f.lower().endswith((".flac",".mp3",".m4a",".ogg",".ape")):
                    audio_file = target / f
                    break
        elif target.is_file():
            audio_file = target
        if audio_file and audio_file.suffix.lower() == '.flac':
            from mutagen.flac import FLAC
            audio = FLAC(str(audio_file))
            if audio.pictures:
                from fastapi.responses import Response
                return Response(content=audio.pictures[0].data, media_type="image/jpeg")
        elif audio_file and audio_file.suffix.lower() == '.mp3':
            from mutagen.id3 import ID3
            tags = ID3(str(audio_file))
            for tag in tags.values():
                if hasattr(tag, 'data') and tag.FrameID == 'APIC':
                    from fastapi.responses import Response
                    return Response(content=tag.data, media_type="image/jpeg")
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="No cover")



@app.post("/api/clear")
async def clear_queue():
    try:
        c = get_mpd()
        c.clear()
        c.disconnect()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/add")
async def add_to_queue(data: dict):
    try:
        c = get_mpd()
        c.add(data.get("file", ""))
        c.disconnect()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Music paths config
MUSIC_PATHS_FILE = Path('/etc/vanadium/music-paths.json')

def load_music_paths():
    MUSIC_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if MUSIC_PATHS_FILE.exists():
        return json.loads(MUSIC_PATHS_FILE.read_text())
    return [{"path": MUSIC_DIR, "samba": True}]

def save_music_paths(paths):
    MUSIC_PATHS_FILE.write_text(json.dumps(paths, indent=2))

def update_samba(paths):
    import subprocess, re
    try:
        with open("/etc/samba/smb.conf") as f:
            smb_conf = f.read()
        smb_conf = re.sub(r"\n\[music[^\]]*\][^\[]*", "", smb_conf, flags=re.DOTALL)
        smb_conf = smb_conf.strip()
        for i, p in enumerate(paths):
            if not p.get("samba"): continue
            share_name = "music" if i == 0 else "music" + str(i+1)
            label = p.get("label", p["path"].split("/")[-1] or "music")
            smb_conf += "\n\n[" + share_name + "]\n"
            smb_conf += "   comment = " + label + "\n"
            smb_conf += "   path = " + p["path"] + "\n"
            smb_conf += "   browseable = yes\n"
            smb_conf += "   read only = no\n"
            smb_conf += "   guest ok = yes\n"
            smb_conf += "   force user = root\n"
        with open("/etc/samba/smb.conf", "w") as f:
            f.write(smb_conf)
        subprocess.run(["systemctl", "restart", "smbd"], capture_output=True)
    except Exception as e:
        print("update_samba error:", e)

@app.get("/api/music-paths")
async def get_music_paths():
    import shutil
    paths = load_music_paths()
    result = []
    for p in paths:
        try:
            usage = shutil.disk_usage(p["path"])
            result.append({"path": p["path"], "samba": p.get("samba", False),
                          "total": usage.total, "used": usage.used, "free": usage.free})
        except:
            result.append({"path": p["path"], "samba": p.get("samba", False),
                          "total": 0, "used": 0, "free": 0})
    return {"ok": True, "paths": result}

@app.post("/api/music-paths/add")
async def add_music_path(data: dict):
    path = data.get("path", "").strip()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=400, detail="Path not found")
    paths = load_music_paths()
    if not any(p["path"] == path for p in paths):
        paths.append({"path": path, "samba": False})
        save_music_paths(paths)
    return {"ok": True}

@app.post("/api/music-paths/remove")
async def remove_music_path(data: dict):
    path = data.get("path", "")
    paths = load_music_paths()
    paths = [p for p in paths if p["path"] != path]
    save_music_paths(paths)
    update_samba(paths)
    return {"ok": True}

@app.post("/api/music-paths/samba")
async def toggle_samba_path(data: dict):
    path = data.get("path", "")
    paths = load_music_paths()
    for p in paths:
        if p["path"] == path:
            p["samba"] = not p.get("samba", False)
    save_music_paths(paths)
    update_samba(paths)
    samba = next((p["samba"] for p in paths if p["path"] == path), False)
    return {"ok": True, "samba": samba}

uvicorn.run(app, host="0.0.0.0", port=8080)
