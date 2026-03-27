# Vanadium OS Player

MPD-based music player with integrated storage management UI.

## Architecture

```
player/
├── api/
│   ├── app.py          # FastAPI backend (MPD control + Storage management)
│   └── requirements.txt
└── ui/
    └── themes/
        ├── neumorphism.html   # Default dark theme
        └── liquid-glass.html  # Liquid glass theme
```

## API Endpoints

### Playback
- `GET  /api/status`     — Current playback status
- `POST /api/play`       — Play
- `POST /api/pause`      — Pause
- `POST /api/next`       — Next track
- `POST /api/prev`       — Previous track
- `POST /api/stop`       — Stop
- `POST /api/volume`     — Set volume `{"volume": 0-100}`
- `POST /api/seek`       — Seek `{"position": seconds}`
- `POST /api/repeat`     — Toggle repeat
- `POST /api/random`     — Toggle random

### Library
- `GET  /api/library`    — Browse music library
- `POST /api/search`     — Search `{"query": "..."}`
- `POST /api/play_file`  — Play file `{"file": "path"}`
- `GET  /api/queue`      — Current queue

### Storage
- `GET  /api/disks`      — List all disks
- `GET  /api/mounts`     — List mount points
- `POST /api/mount`      — Mount disk
- `POST /api/umount`     — Unmount disk
- `POST /api/fstab/add`  — Add to fstab
- `GET  /api/system`     — CPU/memory/Roon status

## Routes
- `/`              — Neumorphism player (default)
- `/storage`       — Storage management UI
- `/player-glass`  — Liquid glass player

## Setup

```bash
pip install -r api/requirements.txt
python api/app.py
```

Server runs on port 8080.

## MPD Config

Music directory: `/home/music`

```
audio_output {
    type "alsa"
    name "Amanero USB DAC"
    device "hw:0,0"
    format "*:*:*"
    auto_resample "no"
}
```
