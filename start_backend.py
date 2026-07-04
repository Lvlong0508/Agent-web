import os
import subprocess

backend_dir = os.path.join(os.path.dirname(__file__), "backend")
cmd = f'cd /d "{backend_dir}" && conda activate agent-web && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000'

subprocess.run(cmd, shell=True)
