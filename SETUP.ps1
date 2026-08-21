param(
    [switch]$NoShortcut,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

$Project = $PSScriptRoot
$Venv = Join-Path $Project ".venv-win"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvPythonw = Join-Path $Venv "Scripts\pythonw.exe"
$Log = Join-Path $Project "setup.log"
$RuntimeDir = Join-Path $Project "runtimes"
$DenoExe = Join-Path $RuntimeDir "deno.exe"

function Find-Python {
    $candidates = @(
        @("py", "-3"),
        @("python", "")
    )

    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $arg = $candidate[1]
        try {
            if ($arg) {
                & $exe $arg -c "import sys; print(sys.version)" *> $null
            } else {
                & $exe -c "import sys; print(sys.version)" *> $null
            }
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {}
    }
    throw "Python 3 was not found. Install Python 3.10+ from https://www.python.org/downloads/windows/ and enable 'Add python.exe to PATH'."
}

function Run-Python {
    param([string[]]$PythonCommand, [string[]]$Arguments)

    if ($PythonCommand.Count -eq 2 -and $PythonCommand[1]) {
        & $PythonCommand[0] $PythonCommand[1] @Arguments
    } else {
        & $PythonCommand[0] @Arguments
    }
}

function New-Shortcut {
    param(
        [string]$Path,
        [string]$Target,
        [string]$Arguments,
        [string]$WorkingDirectory
    )

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $Target
    $Shortcut.Arguments = $Arguments
    $Shortcut.WorkingDirectory = $WorkingDirectory
    $Shortcut.IconLocation = $Target
    $Shortcut.Save()
}

function Install-DenoRuntime {
    if (Test-Path -LiteralPath $DenoExe) {
        return
    }

    Write-Host "Installing Deno runtime..."
    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
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

try {
    "==== Setup ====" | Set-Content -Path $Log -Encoding UTF8
    Set-Location -LiteralPath $Project

    if ($Update) {
        Write-Host "Updating YTET engine and dependencies..." -ForegroundColor Cyan
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            throw "Virtual environment was not found. Please run setup without -Update first."
        }
        & $VenvPython -m pip install --upgrade "yt-dlp[default]" yt-dlp-ejs 2>&1 | Tee-Object -FilePath $Log -Append
        if ($LASTEXITCODE -ne 0) { throw "Update failed. See log: $Log" }
        Write-Host ""
        Write-Host "Engine updated successfully to latest version." -ForegroundColor Green
        return
    }

    Write-Host "Setting up YTET..." -ForegroundColor Cyan
    $PythonCommand = Find-Python

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "Creating virtual environment..."
        Run-Python -PythonCommand $PythonCommand -Arguments @("-m", "venv", $Venv)
    }

    Write-Host "Installing dependencies..."
    & $VenvPython -m pip install --upgrade pip 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed. See log: $Log" }

    & $VenvPython -m pip install -r requirements.txt 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. See log: $Log" }

    & $VenvPython -m pip install --no-deps -e . 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { throw "Package installation failed. See log: $Log" }

    Install-DenoRuntime 2>&1 | Tee-Object -FilePath $Log -Append

    if (-not $NoShortcut) {
        if (-not (Test-Path -LiteralPath $VenvPythonw)) {
            throw "pythonw.exe was not found in the virtual environment."
        }
        $Desktop = [Environment]::GetFolderPath("Desktop")
        $Launcher = Join-Path $Desktop "YTET.lnk"
        $OldLauncher = Join-Path $Desktop "YouTube Audio Extractor.lnk"
        $RunApp = Join-Path $Project "run_app.py"
        New-Shortcut -Path $Launcher -Target $VenvPythonw -Arguments "`"$RunApp`"" -WorkingDirectory $Project
        if (Test-Path -LiteralPath $OldLauncher) {
            Remove-Item -LiteralPath $OldLauncher -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Desktop shortcut: $Launcher"
    }

    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
    Write-Host "Run YTET.cmd to start."
    Write-Host ""
    Read-Host "Press Enter to close"
}
catch {
    Add-Content -Path $Log -Value "ERROR: $($_.Exception.Message)" -Encoding UTF8
    Write-Host ""
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log: $Log"
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}
