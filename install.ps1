# Smart-Screen installer. Run install.bat (it starts this as administrator).
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Dir
$TaskName = "Smart-Screen"

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "   $t" -ForegroundColor Green }
function Warn($t) { Write-Host "   $t" -ForegroundColor Yellow }

Write-Host "Smart-Screen installer" -ForegroundColor White
Write-Host "Folder: $Dir"

# ---------------------------------------------------------------- old app
Step "Old UsbMonitor software"
$old = Get-Process -Name "UsbMonitor" -ErrorAction SilentlyContinue
if ($old) { $old | Stop-Process -Force; Ok "Closed UsbMonitor.exe (it keeps the screen's COM port busy)" }
else { Ok "UsbMonitor.exe is not running" }

$oldTasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.State -ne "Disabled" -and ($_.Actions | Where-Object { $_.Execute -like "*UsbMonitor*" }) })
$runKeys = @()
foreach ($k in "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run", "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run",
               "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run") {
    if (Test-Path $k) {
        $p = Get-ItemProperty $k
        foreach ($n in $p.PSObject.Properties.Name) {
            if ("$($p.$n)" -like "*UsbMonitor*") { $runKeys += [pscustomobject]@{Key = $k; Name = $n; Value = $p.$n } }
        }
    }
}
if ($oldTasks.Count -or $runKeys.Count) {
    $oldTasks | ForEach-Object { Write-Host "   autostart task: $($_.TaskName)" }
    $runKeys  | ForEach-Object { Write-Host "   autostart entry: $($_.Name) -> $($_.Value)" }
    $a = Read-Host "   Turn off the old UsbMonitor autostart? Both apps cannot use the screen at once. [Y/n]"
    if ($a -notmatch "^[nN]") {
        $oldTasks | ForEach-Object { Disable-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath | Out-Null }
        $backup = Join-Path $Dir "old-autostart-backup.txt"
        foreach ($r in $runKeys) {
            Add-Content $backup "$($r.Key) | $($r.Name) | $($r.Value)"
            Remove-ItemProperty -Path $r.Key -Name $r.Name
        }
        Ok "Old autostart turned off (tasks disabled; Run entries saved to old-autostart-backup.txt)"
    }
} else { Ok "No old autostart found" }

# ---------------------------------------------------------------- python
Step "Python"
function Test-Py($cand) {
    # True if the command runs a real Python 3.10+ (the Microsoft Store "python" alias fails here)
    try {
        $v = & $cand[0] $cand[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$v" -match "^3\.(\d+)$" -and [int]$Matches[1] -ge 10)
    } catch { return $false }
}
function Find-Py {
    $cands = @(@("py", "-3"), @("python"))
    foreach ($pat in "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-3*\python.exe",
                     "$env:ProgramFiles\Python3*\python.exe") {
        Get-ChildItem $pat -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { $cands += , @($_.FullName) }
    }
    foreach ($c in $cands) { if (Test-Py $c) { return , $c } }
    return $null
}
$py = Find-Py
if (-not $py) {
    Warn "Python 3.10+ not found - installing Python 3.14 with winget..."
    $ErrorActionPreference = "Continue"
    try { winget install -e --id Python.Python.3.14 --source winget --scope machine --silent --accept-package-agreements --accept-source-agreements } catch { }
    $ErrorActionPreference = "Stop"
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Find-Py
    if (-not $py) { Write-Host "Python install failed. Install Python from https://www.python.org/downloads/ (tick 'Add to PATH') and run install.bat again." -ForegroundColor Red; Read-Host "Enter to exit"; exit 1 }
}
$pyver = & $py[0] $py[1..9] -c "import sys; print(sys.version.split()[0])"
Ok "Using Python $pyver"

Step "Virtual environment + packages"
$venv = Join-Path $Dir ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
if ((Test-Path $venv) -and -not (Test-Py @($venvPy))) {
    # e.g. folder copied from another PC/user: the venv points to a Python that is not here
    Warn "Existing .venv is broken (its Python is missing) - rebuilding it"
    Remove-Item -Recurse -Force $venv
}
if (-not (Test-Path $venvPy)) {
    & $py[0] $py[1..9] -m venv $venv
    if (-not (Test-Py @($venvPy))) { Write-Host "Could not create the virtual environment in $venv." -ForegroundColor Red; Read-Host "Enter to exit"; exit 1 }
}
$ErrorActionPreference = "Continue"
& $venvPy -m pip install --disable-pip-version-check -q --no-index --find-links (Join-Path $Dir "wheels") -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Warn "Offline packages did not fit this Python version - downloading from PyPI..."
    & $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "Package install failed. Check your internet/VPN and run install.bat again." -ForegroundColor Red; Read-Host "Enter to exit"; exit 1 }
}
$ErrorActionPreference = "Stop"
Ok "Packages installed"

# ---------------------------------------------------------------- PawnIO (CPU temperature driver for LibreHardwareMonitor)
Step "PawnIO driver (needed for CPU temperatures)"
$svc = Get-Service -Name "PawnIO" -ErrorAction SilentlyContinue
if ($svc) { Ok "PawnIO already installed" }
else {
    $setup = Join-Path $Dir "external\PawnIO\PawnIO_setup.exe"
    $p = Start-Process -FilePath $setup -ArgumentList "-install", "-silent" -Wait -PassThru
    if ($p.ExitCode -eq 0) { Ok "PawnIO installed" } else { Warn "PawnIO setup returned $($p.ExitCode) - CPU temperature may be missing" }
}

# ---------------------------------------------------------------- autostart task
Step "Autostart at logon (as administrator, no UAC prompt)"
$pyw = Join-Path $Dir ".venv\Scripts\pythonw.exe"
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$(Join-Path $Dir 'main.py')`"" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT10S"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Ok "Task '$TaskName' created"

Step "Starting Smart-Screen"
try { cmd /c "`"$(Join-Path $Dir 'stop.bat')`" >nul 2>&1" } catch { }
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName $TaskName
Ok "Started. Look for the Smart-Screen icon next to the clock (it may be in the ^ overflow menu)."
Write-Host "`nDone. Right-click the tray icon for themes, pages, orientation, brightness and Settings." -ForegroundColor White
Read-Host "Press Enter to close"
