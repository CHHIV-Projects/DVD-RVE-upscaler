# DVD RVE Upscaler

This repository contains the LAN-only FastAPI operator application for discovering, analyzing, preparing, and enhancing DVD originals.

## Local development

```bash
cd /home/chuck/projects/DVD-RVE-upscaler
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Then open the single operator workflow in a browser at:

- http://127.0.0.1:8010/media
- or the host LAN URL on the same private network: http://192.168.1.173:8010/media

The LAN URL is the intended target for a future Windows browser shortcut. The application discovers originals only from configured trusted NAS locations and performs preparation, enhancement, and final stream-copy remux on server-local storage. Publication is explicit, collision-safe, and fail-closed unless `/mnt/nas/dvd-upscaled-publication` is a distinct narrow writable NAS mount; the broad Movies mount is never used for publication. The narrow root may be configured with `DVD_RVE_PUBLICATION_ROOT`.
