# Unstick Docker Desktop on Windows when it refuses to start.
#
# Symptom: Docker Desktop opens, shows "Docker Desktop encountered an
# unexpected error and needs to close", and the daemon never comes up. The log
# (%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log) ends with:
#
#     backend cancelling with error: starting services: initializing
#     Inference manager: listening on unix://.../dockerInference:
#     remove .../dockerInference: The file cannot be accessed by the system.
#
# ...or the same line naming the Secrets Engine and engine.sock.
#
# Cause: Docker leaves AF_UNIX socket files on disk. On an unclean shutdown
# they can be left in a state where Windows refuses EVERY access to them --
# error 1920, "the file cannot be accessed by the system". They cannot be
# read, deleted, renamed, or even have their reparse point stripped;
# Remove-Item, `rd /s /q`, raw \\?\ paths and `fsutil reparsepoint delete` all
# fail identically. Docker then crashes trying to remove one before
# re-listening on it.
#
# Fix: the socket files are runtime scratch, recreated on every start, so we
# move the whole directory aside instead of fighting the file. Nothing is
# deleted -- the moved directories clear on a reboot, once Windows releases
# the handles.
#
# If this keeps happening, the underlying cause is probably antivirus holding
# the files (AVG has damaged this project's working tree before). Excluding
# these paths from real-time scanning should stop it for good:
#     %LOCALAPPDATA%\Docker
#     %LOCALAPPDATA%\docker-secrets-engine
#     C:\ProgramData\Docker
#
# Usage, from the repo root:
#     powershell -ExecutionPolicy Bypass -File scripts\fix_docker_sockets.ps1

$ErrorActionPreference = 'Stop'

Write-Host "Stopping Docker Desktop..."
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match 'docker' } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$targets = @(
    "$env:LOCALAPPDATA\Docker\run",
    "$env:LOCALAPPDATA\docker-secrets-engine"
)

foreach ($dir in $targets) {
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    $aside = "$dir.stale-$stamp"
    try {
        Move-Item -LiteralPath $dir -Destination $aside -Force
        Write-Host "  moved $(Split-Path $dir -Leaf) aside"
    } catch {
        Write-Warning "  could not move $dir : $($_.Exception.Message)"
        Write-Warning "  reboot and run this again."
    }
}

$exe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe
    Write-Host "Docker Desktop relaunched. The daemon takes 1-4 minutes."
    Write-Host "Check with:  docker info"
} else {
    Write-Warning "Docker Desktop not found at $exe - start it yourself."
}

# The aside directories accumulate. They are empty scratch; delete them after
# a reboot whenever you like.
$stale = Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Docker" -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'stale|broken' }
if ($stale) {
    Write-Host ""
    Write-Host "Old aside directories (safe to delete after a reboot):"
    $stale | ForEach-Object { Write-Host "  $($_.FullName)" }
}
