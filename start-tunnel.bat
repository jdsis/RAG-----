@echo off
cd /d F:\Python\fastApiProject
:loop
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:11434 --protocol http2 --no-autoupdate >> F:\Python\fastApiProject\cf-tunnel.log 2>&1
timeout /t 5 /nobreak >nul
goto loop
