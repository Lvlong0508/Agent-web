import os
import subprocess

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "AgentWeb-user")
os.chdir(frontend_dir)

subprocess.run(f'for /f "tokens=2" %a in (\'tasklist /fi "imagename eq node.exe" /nh ^| findstr /i vite\') do taskkill /f /pid %a >nul 2>&1', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

subprocess.run("npm run dev", shell=True)
