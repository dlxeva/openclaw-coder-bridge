Set oShell = CreateObject("WScript.Shell")
' 填入你的 OpenClaw Telegram Bot Token 和你的 Telegram Chat ID
oShell.Environment("Process")("TELEGRAM_BOT_TOKEN") = "YOUR_BOT_TOKEN_HERE"
oShell.Environment("Process")("TELEGRAM_CHAT_ID") = "YOUR_CHAT_ID_HERE"
' Path to coder-bridge.py — adjust as needed
oShell.Run "cmd.exe /c python ""%USERPROFILE%\.openclaw\workspace\skills\brain\opencode\coder-bridge.py""", 0, False
