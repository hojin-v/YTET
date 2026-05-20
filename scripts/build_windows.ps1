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

$RuntimeDir = Join-Path $Project "build\runtimes"
$DenoExe = Join-Path $RuntimeDir "deno.exe"
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $DenoExe)) {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/denoland/deno/releases/latest"
    $Asset = $Release.assets | Where-Object { $_.name -eq "deno-x86_64-pc-windows-msvc.zip" } | Select-Object -First 1
    if (-not $Asset) {
        throw "Could not find Deno Windows x64 release asset."
    }
    $DenoZip = Join-Path $RuntimeDir "deno.zip"
    Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $DenoZip
    Expand-Archive -LiteralPath $DenoZip -DestinationPath $RuntimeDir -Force
    Remove-Item -LiteralPath $DenoZip -Force
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name YTET `
    --paths src `
    --collect-all imageio_ffmpeg `
    --collect-all yt_dlp_ejs `
    --collect-submodules yt_dlp `
    --add-binary "$DenoExe;runtimes" `
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
