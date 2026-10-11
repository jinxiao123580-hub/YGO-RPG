@echo off
title YGO-RPG Bot Duel (Spectate via MDPro3)
rem ===== One-click bot duel. Spectate: MDPro3 -> Online -> server "Local 7911" -> any room name -> Join =====
taskkill /IM WindBot.exe /F >nul 2>&1
taskkill /IM YGOSharp.exe /F >nul 2>&1

echo [1/4] Starting duel server on port 7911 ...
cd /d E:\FUN\YGO-RPG\YGO\ygosharp\YGOSharp\bin\Release
start "ygo-server" /MIN YGOSharp.exe Config=server.conf
timeout /t 2 /nobreak >nul

echo [2/4] Starting mock LLM endpoint on port 5757 ...
start "mock-llm" /MIN node E:\FUN\YGO-RPG\YGO\windbot-llm\tools\mock-llm.js
timeout /t 1 /nobreak >nul

echo [3/4] Red bot (script AI, host) entering ...
cd /d E:\FUN\YGO-RPG\YGO\windbot-llm\bin\Release
start "botA-ScriptAI" /MIN WindBot.exe Name=Red_ScriptAI Deck=Blue-Eyes Host=127.0.0.1 Port=7911 Version=4945
timeout /t 3 /nobreak >nul

echo [4/4] Blue bot (LLM brain) entering ...
start "botB-LLM" /MIN WindBot.exe Name=Blue_LLMBot Deck=Blue-Eyes Host=127.0.0.1 Port=7911 Version=4945 LLMEnabled=True LLMEndpoint=http://127.0.0.1:5757/v1/chat/completions LLMTimeout=3000 LLMPersona=TestPersona LLMMercy=2

echo.
echo  ==================================================
echo   DUEL IS LIVE (16000 LP, ~5-8 min)
echo   NOW open MDPro3: Online - Local 7911 - any name - Join
echo   Joining mid-duel = auto spectator
echo   Missed it? Just double-click this file again.
echo  ==================================================
pause
