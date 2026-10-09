@echo off
rem Ask the running Smart-Screen to quit (same as tray icon - Quit)
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 47815); $s = $c.GetStream(); $b = [Text.Encoding]::ASCII.GetBytes('quit'); $s.Write($b, 0, $b.Length); $c.Close(); 'Smart-Screen stopped.' } catch { 'Smart-Screen is not running.' }"
