param(
    [string]$Python = "python",
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"

$Project = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $Project

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install -r requirements-dev.txt
& $Python -m pip install --no-deps -e .

Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "dist" -Recurse -Force -ErrorAction SilentlyContinue

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name YTET `
    --paths src `
    --collect-all imageio_ffmpeg `
    --collect-submodules yt_dlp `
    run_app.py

$PackageDir = Join-Path $Project "dist\package"
New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null
Copy-Item -LiteralPath "dist\YTET.exe" -Destination (Join-Path $PackageDir "YTET.exe") -Force
Copy-Item -LiteralPath "README.md" -Destination (Join-Path $PackageDir "README.md") -Force

$ZipPath = Join-Path $Project "dist\YTET-$Version-windows-x64.zip"
Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force

Write-Host "Built: dist\YTET.exe"
Write-Host "Built: $ZipPath"
