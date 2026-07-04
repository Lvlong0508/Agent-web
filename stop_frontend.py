import subprocess
subprocess.run(
    'for /f "tokens=2" %a in (\'tasklist /fi "imagename eq node.exe" /nh ^| findstr /i vite\') do taskkill /f /pid %a >nul 2>&1',
    shell=True
)
print("Frontend stopped.")
