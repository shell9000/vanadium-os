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
PROXY_HOST = "192.168.0.1"
PROXY_PORT = 7891
PROXY_USER = "Clash"
PROXY_PASS = "OUsqx5pp"

def fetch_via_proxy(url, headers=None, timeout=8, ua="VanadiumOS/1.0"):
    """Fetch URL via curl, clearing proxy env vars for direct access"""
    import subprocess, os
    env = os.environ.copy()
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','all_proxy']:
        env.pop(k, None)
    cmd = ["curl", "-s", "-L", "-m", str(timeout), "-A", ua]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, timeout=timeout+2, env=env)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise Exception(f"curl failed: rc={result.returncode} len={len(result.stdout)}")

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


@app.get("/api/artists")
async def get_artists():
    try:
        c = get_mpd()
        # Get all artists from MPD (fast)
        raw = c.list("artist")
        # Also albumartist
        try:
            raw2 = c.list("albumartist")
        except:
            raw2 = []
        c.disconnect()

        import re
        artist_map = {}
        for item in list(raw) + list(raw2):
            a = item.get("artist", item.get("albumartist", "")) if isinstance(item, dict) else str(item)
            a = a.strip()
            if not a: continue
            # Filter: reject if 3+ consecutive ? (broken encoding)
            if re.search(r'\?{3,}', a): continue
            # Filter: reject high ratio of non-CJK/Latin chars
            valid = sum(1 for c in a if (
                0x0020 <= ord(c) <= 0x024F or
                0x4E00 <= ord(c) <= 0x9FFF or
                0x3040 <= ord(c) <= 0x30FF or
                0xAC00 <= ord(c) <= 0xD7AF or
                0xFF00 <= ord(c) <= 0xFFEF or
                0x0370 <= ord(c) <= 0x03FF
            ))
            if valid / max(len(a), 1) < 0.6: continue
            artist_map[a] = artist_map.get(a, 0) + 1

        result = [{"name": a, "count": v} for a, v in sorted(artist_map.items(), key=lambda x: x[0].lower())]
        return {"ok": True, "artists": result}
    except Exception as e:
        return {"ok": False, "artists": [], "error": str(e)}

@app.get("/api/artist-albums")
async def get_artist_albums(artist: str = ""):
    try:
        c = get_mpd()
        # Use find (exact) first, fallback to search (slower)
        try:
            results = c.find("artist", artist)
            if not results:
                results = c.find("albumartist", artist)
        except:
            results = c.search("artist", artist)
        c.disconnect()
        # Group by parent directory (album level)
        dirs_seen = set()
        albums = []
        for item in results:
            f = item.get("file", "")
            parts = f.split("/")
            # Use parent dir of file as album dir
            if len(parts) >= 2:
                album_dir = "/".join(parts[:-1])
            else:
                album_dir = parts[0] if parts else ""
            if album_dir and album_dir not in dirs_seen:
                dirs_seen.add(album_dir)
                albums.append({"directory": album_dir})
        albums.sort(key=lambda x: x["directory"].lower())
        return {"ok": True, "albums": albums}
    except Exception as e:
        return {"ok": False, "albums": [], "error": str(e)}

AUDIO_CONFIG_FILE = Path('/etc/vanadium/audio-config.json')

def load_audio_config():
    AUDIO_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if AUDIO_CONFIG_FILE.exists():
        try:
            return json.loads(AUDIO_CONFIG_FILE.read_text())
        except: pass
    return {"mixer": False, "resample": False, "dop": False, "cpu": False, "buffer": "8192"}

def save_audio_config(cfg):
    AUDIO_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUDIO_CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def apply_audio_config(cfg):
    import subprocess
    # Read current mpd.conf
    mpd_conf = Path("/etc/mpd.conf").read_text()
    # Update audio_buffer_size
    import re
    buf = cfg.get("buffer", "8192")
    mpd_conf = re.sub(r'audio_buffer_size "[^"]+"', f'audio_buffer_size "{buf}"', mpd_conf)
    if 'audio_buffer_size' not in mpd_conf:
        mpd_conf += f'\naudio_buffer_size "{buf}"\n'
    # Update mixer_type in audio_output block
    mixer_val = 'software' if cfg.get('mixer') else 'none'
    mpd_conf = re.sub(r'mixer_type "[^"]+"', f'mixer_type "{mixer_val}"', mpd_conf)
    # Update dop
    dop_val = 'yes' if cfg.get('dop') else 'no'
    mpd_conf = re.sub(r'dop "[^"]+"', f'dop "{dop_val}"', mpd_conf)
    # Write back
    Path("/etc/mpd.conf").write_text(mpd_conf)
    # CPU governor
    if cfg.get('cpu'):
        for f in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor'):
            try: f.write_text('performance')
            except: pass
    else:
        for f in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor'):
            try: f.write_text('powersave')
            except: pass
    # Restart MPD
    subprocess.run(['pkill', '-x', 'mpd'], capture_output=True)
    import time; time.sleep(1)
    subprocess.run(['systemctl', 'start', 'mpd'], capture_output=True)
    return True

@app.get("/api/audio-config")
async def get_audio_config():
    return {"ok": True, "config": load_audio_config()}

@app.post("/api/audio-config")
async def set_audio_config(data: dict):
    key = data.get("key")
    val = data.get("value")
    cfg = load_audio_config()
    if key in cfg:
        cfg[key] = val
        save_audio_config(cfg)
        apply_audio_config(cfg)
        return {"ok": True, "restart": True}
    raise HTTPException(status_code=400, detail="Unknown key")

import urllib.request
import urllib.parse

ARTIST_IMAGE_CACHE = {}  # in-memory cache
ARTIST_CACHE_FILE = Path("/etc/vanadium/artist-image-cache.json")

def load_artist_cache():
    global ARTIST_IMAGE_CACHE
    if ARTIST_CACHE_FILE.exists():
        try:
            ARTIST_IMAGE_CACHE = json.loads(ARTIST_CACHE_FILE.read_text())
        except: pass

def save_artist_cache():
    ARTIST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ARTIST_CACHE_FILE.write_text(json.dumps(ARTIST_IMAGE_CACHE, ensure_ascii=False))

load_artist_cache()

@app.get("/api/artist-image")
async def get_artist_image(name: str = ""):
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if name in ARTIST_IMAGE_CACHE:
        return {"ok": True, "url": ARTIST_IMAGE_CACHE[name]}
    HEADERS = {"User-Agent": "VanadiumOS/1.0 +https://vvaudiolab.com"}
    try:
        import time
        img = None
        q = urllib.parse.quote(name)

        # Step 1: iTunes Search API (best coverage for pop/Canto/Classical)
        try:
            itunes_url = f"https://itunes.apple.com/search?term={q}&entity=song&limit=1"
            raw = fetch_via_proxy(itunes_url, timeout=8)
            idata = json.loads(raw.strip())
            for r2 in idata.get("results", []):
                img = r2.get("artworkUrl100", "").replace("100x100bb", "600x600bb").replace("100x100", "600x600")
                if img: break
        except: pass

        if img:
            ARTIST_IMAGE_CACHE[name] = img
            save_artist_cache()
            return {"ok": True, "url": img}

        # Step 2: NetEase Music API via local NeteaseCloudMusicApi (port 3001)
        try:
            ne_url = f"http://127.0.0.1:3001/search?keywords={q}&type=100&limit=3"
            raw_ne = fetch_via_proxy(ne_url, timeout=5)
            if raw_ne:
                ne_data = json.loads(raw_ne)
                artists_ne = ne_data.get("result",{}).get("artists",[])
                for a in artists_ne:
                    pic = a.get("picUrl","")
                    if pic and "default" not in pic:
                        img = pic.replace("http://", "https://")
                        break
        except Exception as _nee:
            pass

        if img:
            ARTIST_IMAGE_CACHE[name] = img
            save_artist_cache()
            return {"ok": True, "url": img}

        # Step 2b: QQ Music API
        try:
            qq_url = f"https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp?w={q}&p=1&n=1&format=json&inCharset=utf8&outCharset=utf-8&platform=yqq&needNewCode=0&catZhida=1&zhidaqu=1&t=0&aggr=0&lossless=0&sem=1&cid=205360838&new_json=1"
            raw_qq = fetch_via_proxy(qq_url, timeout=8)
            if raw_qq:
                qq_data = json.loads(raw_qq)
                singer_list = qq_data.get("data",{}).get("zhida",{}).get("singerlist",[])
                if not singer_list:
                    singer_list = qq_data.get("data",{}).get("singer",{}).get("singerlist",[])
                for s in singer_list:
                    singer_mid = s.get("singermid","")
                    if singer_mid:
                        img = f"https://y.gtimg.cn/music/photo_new/T001R300x300M000{singer_mid}.jpg"
                        break
        except Exception as _qqe:
            pass

        if img:
            ARTIST_IMAGE_CACHE[name] = img
            save_artist_cache()
            return {"ok": True, "url": img}

        # Step 2b: MusicBrainz + Wikidata fallback
        try:
            mb_url = f"https://musicbrainz.org/ws/2/artist/?query={q}&fmt=json&limit=1"
            raw_mb = fetch_via_proxy(mb_url, timeout=8)
            mb_data = json.loads(raw_mb)
            artists_mb = mb_data.get("artists", [])
            if artists_mb:
                mbid = artists_mb[0].get("id", "")
                if mbid:
                    # Get relations for Wikidata ID
                    rel_url = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels&fmt=json"
                    raw_rel = fetch_via_proxy(rel_url, timeout=8)
                    rel_data = json.loads(raw_rel)
                    wd_id = None
                    for rel in rel_data.get("relations", []):
                        if rel.get("type") == "wikidata":
                            wd_url = rel.get("url", {}).get("resource", "")
                            wd_id = wd_url.split("/")[-1] if wd_url else None
                            break
                    if wd_id:
                        wd_api = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wd_id}&props=claims&format=json"
                        raw_wd = fetch_via_proxy(wd_api, timeout=8)
                        wd_data = json.loads(raw_wd)
                        claims = wd_data.get("entities", {}).get(wd_id, {}).get("claims", {})
                        p18 = claims.get("P18", [])
                        if p18:
                            fname = p18[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
                            if fname:
                                fname = fname.replace(" ", "_")
                                img = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(fname)}"
        except Exception as _mbe:
            print(f"[mb-fallback] {_mbe}")

        if img:
            ARTIST_IMAGE_CACHE[name] = img
            save_artist_cache()
            return {"ok": True, "url": img}

        # Step 4: Discogs fallback
        time.sleep(0.3)
        try:
            search_url = f"https://api.discogs.com/database/search?q={q}&type=artist&per_page=3"
            req2 = urllib.request.Request(search_url, headers=HEADERS)
            with urllib.request.urlopen(req2, timeout=6) as resp2:
                data = json.loads(resp2.read())
            for r in data.get("results", []):
                for k in ["cover_image", "thumb"]:
                    v = r.get(k, "")
                    if v and "spacer" not in v:
                        img = v
                        break
                if img: break
                resource_url = r.get("resource_url", "")
                if resource_url:
                    try:
                        req3 = urllib.request.Request(resource_url, headers=HEADERS)
                        with urllib.request.urlopen(req3, timeout=6) as resp3:
                            detail = json.loads(resp3.read())
                        for im in detail.get("images", []):
                            uri = im.get("uri") or im.get("uri150", "")
                            if uri and "spacer" not in uri:
                                img = uri
                                break
                    except: pass
                if img: break
        except: pass
        ARTIST_IMAGE_CACHE[name] = ""
        save_artist_cache()
        return {"ok": False, "url": ""}
    except Exception as e:
        return {"ok": False, "url": "", "error": str(e)}

from fastapi.responses import Response as FastAPIResponse

@app.get("/api/artist-image-proxy")
async def artist_image_proxy(name: str = ""):
    """Proxy artist image through backend to avoid CORS/GFW issues"""
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    # Get URL first
    r = await get_artist_image(name)
    url = r.get("url", "") if isinstance(r, dict) else ""
    if not url:
        raise HTTPException(status_code=404, detail="No image found")
    try:
        HEADERS = {"User-Agent": "VanadiumOS/1.0 +https://vvaudiolab.com"}
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "image/jpeg")
        return FastAPIResponse(content=data, media_type=ct)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

import asyncio
import threading

def prefetch_artist_images():
    """Background thread: prefetch all artist images on startup"""
    import time
    time.sleep(10)  # Wait for server to fully start
    try:
        c = get_mpd()
        raw = c.list("artist")
        try:
            raw2 = c.list("albumartist")
        except:
            raw2 = []
        c.disconnect()
        import re
        artists = set()
        for item in list(raw) + list(raw2):
            a = item.get("artist", item.get("albumartist", "")) if isinstance(item, dict) else str(item)
            a = a.strip()
            if not a: continue
            if re.search(r'\?{3,}', a): continue
            valid = sum(1 for ch in a if (
                0x0020 <= ord(ch) <= 0x024F or
                0x4E00 <= ord(ch) <= 0x9FFF or
                0x3040 <= ord(ch) <= 0x30FF or
                0xAC00 <= ord(ch) <= 0xD7AF
            ))
            if valid / max(len(a), 1) < 0.6: continue
            artists.add(a)
        print(f"[prefetch] Starting artist image prefetch for {len(artists)} artists")
        fetched = 0
        for name in sorted(artists):
            if name in ARTIST_IMAGE_CACHE and ARTIST_IMAGE_CACHE[name]:
                continue  # already cached
            try:
                import urllib.parse
                q = urllib.parse.quote(name)
                # Use fetch_via_proxy directly (curl subprocess with socks5)
                itunes_url = f"https://itunes.apple.com/search?term={q}&entity=song&limit=1"
                raw = fetch_via_proxy(itunes_url, timeout=10)
                idata = json.loads(raw.strip())
                img = None
                for r2 in idata.get("results", []):
                    img = r2.get("artworkUrl100", "").replace("100x100bb", "600x600bb").replace("100x100", "600x600")
                    if img: break
                ARTIST_IMAGE_CACHE[name] = img or ""
                if img:
                    fetched += 1
                    print(f"[prefetch] {name}: OK")
                save_artist_cache()
                time.sleep(0.5)
            except Exception as e:
                print(f"[prefetch] {name}: ERROR {e}")
                ARTIST_IMAGE_CACHE[name] = ""
                save_artist_cache()
                time.sleep(0.5)
        print(f"[prefetch] Done: {fetched}/{len(artists)} images fetched")
    except Exception as e:
        print(f"[prefetch] Error: {e}")

# Start prefetch in background thread
_prefetch_thread = threading.Thread(target=prefetch_artist_images, daemon=True)
_prefetch_thread.start()
uvicorn.run(app, host="0.0.0.0", port=8080)
