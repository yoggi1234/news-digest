@echo off
rem Removes this folder from your user PATH (undoes install.bat). Your files are not touched.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = '%~dp0'.TrimEnd('\');" ^
  "$p = [Environment]::GetEnvironmentVariable('Path', 'User');" ^
  "$keep = ($p -split ';') | Where-Object { $_ -and $_ -ne $d };" ^
  "[Environment]::SetEnvironmentVariable('Path', ($keep -join ';'), 'User');" ^
  "Write-Host ('Removed from PATH: ' + $d)"
pause
