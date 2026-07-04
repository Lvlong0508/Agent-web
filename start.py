import os
import subprocess

backend_dir = os.path.join(os.path.dirname(__file__), "backend")
os.chdir(backend_dir)

subprocess.run(
    'for /f "tokens=2" %a in (\'tasklist /fi "imagename eq python.exe" /nh ^| findstr /i uvicorn\') do taskkill /f /pid %a >nul 2>&1',
    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

subprocess.run("uvicorn app.main:app --reload --host 0.0.0.0 --port 8000", shell=True)
