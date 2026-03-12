"""Launch the X Spaces Downloader web UI.

Usage:
    python run_web.py              # http://localhost:8000
    python run_web.py --port 9000
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

import uvicorn

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", default=False)
    args = p.parse_args()

    print(f"\n  X Spaces Downloader UI → http://{args.host}:{args.port}\n")
    uvicorn.run("web_app.main:app", host=args.host, port=args.port, reload=args.reload)
