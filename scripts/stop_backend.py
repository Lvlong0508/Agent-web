import subprocess
subprocess.run(
    'for /f "tokens=2" %a in (\'tasklist /fi "imagename eq python.exe" /nh ^| findstr /i uvicorn\') do taskkill /f /pid %a >nul 2>&1',
    shell=True
)
print("Backend stopped.")
