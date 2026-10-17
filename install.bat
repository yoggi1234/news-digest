@echo off
rem Adds this folder to your user PATH so "digest" works in any terminal, from any folder.
rem Undo with uninstall.bat. Only your own user PATH is changed (no admin rights needed).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = '%~dp0'.TrimEnd('\');" ^
  "$p = [Environment]::GetEnvironmentVariable('Path', 'User');" ^
  "if (($p -split ';') -contains $d) { Write-Host ('Already on PATH: ' + $d) }" ^
  "else { $new = if ($p) { $p.TrimEnd(';') + ';' + $d } else { $d };" ^
  "  [Environment]::SetEnvironmentVariable('Path', $new, 'User');" ^
  "  Write-Host ('Added to PATH: ' + $d) }"
echo.
echo Close this window, open a NEW terminal (cmd, PowerShell or Git Bash) and type:  digest
pause
