# Registers/removes the G510 daemon as a per-user login autostart entry
# (HKCU\...\Run, no admin needed). Runs headless via pythonw.exe.
#   powershell -ExecutionPolicy Bypass -File g510\autostart.ps1            # install
#   powershell -ExecutionPolicy Bypass -File g510\autostart.ps1 -Remove    # uninstall
param([switch]$Remove)

$name = "ClaudeG510Lcd"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if ($Remove) {
    Remove-ItemProperty -Path $runKey -Name $name -ErrorAction SilentlyContinue
    Write-Host "Autostart entry '$name' removed."
    return
}

$pythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$script = Join-Path $PSScriptRoot "daemon.py"
if (-not (Test-Path $pythonw)) { throw "Not found: $pythonw (create the venv first, see README.md)" }

Set-ItemProperty -Path $runKey -Name $name -Value "`"$pythonw`" `"$script`""
Write-Host "Autostart entry '$name' set:"
Write-Host (Get-ItemProperty -Path $runKey -Name $name).$name
