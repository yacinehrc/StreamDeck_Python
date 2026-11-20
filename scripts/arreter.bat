@echo off
rem Arrete StreamDeck Python (fenetre ou arriere-plan).
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*deck_companion.py*' }; if ($p) { $p | Invoke-CimMethod -MethodName Terminate | Out-Null; Write-Host 'StreamDeck Python arrete.' } else { Write-Host 'StreamDeck Python ne tournait pas.' }"
timeout /t 3 >nul
