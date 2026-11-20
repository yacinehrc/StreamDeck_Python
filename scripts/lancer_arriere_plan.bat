@echo off
rem Lance StreamDeck Python sans fenetre. Arret : scripts\arreter.bat
cd /d "%~dp0.."
start "" pyw deck_companion.py
echo StreamDeck Python demarre en arriere-plan (PIN dans config.json).
timeout /t 3 >nul
