# DVD RVE Upscaler

This repository contains the baseline FastAPI application scaffold for the DVD RVE Upscaler browser workflow.

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

Then open the app in a browser at:

- http://127.0.0.1:8010/
- or the host LAN IP on the same private network, for example http://192.168.1.173:8010/

This milestone intentionally does not implement media discovery, FFmpeg analysis, RVE processing, or NAS publication.
