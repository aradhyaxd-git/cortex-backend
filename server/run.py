# run.py
import sys
import os
import uvicorn

# Add src to sys.path so cortex is importable from anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

if __name__ == "__main__":
    from cortex.config import HOST, PORT
    print(f"Starting Cortex QRTOS backend on http://{HOST}:{PORT}")
    uvicorn.run("cortex.main:app", host=HOST, port=PORT, reload=True)
