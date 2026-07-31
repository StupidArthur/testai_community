param(
    [switch]$SkipChromium,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"

# Domestic mirrors (no GitHub)
$NODE_VERSION = "18.20.8"
$NODE_MIRROR = "https://npmmirror.com/mirrors/node"
$NPM_REGISTRY = "https://registry.npmmirror.com"
$PLAYWRIGHT_MIRROR = "https://npmmirror.com/mirrors/playwright"
# Chrome for Testing version (matches playwright-core 1.49.1; available on npmmirror)
$CHROME_CFT_VERSION = "131.0.6778.85"
$CHROME_MIRROR = "https://registry.npmmirror.com/-/binary/chrome-for-testing"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ReleaseDir = Join-Path (Join-Path $ProjectRoot "release") "recorder"
$CacheDir = Join-Path $ProjectRoot ".cache"
$NodeZipName = "node-v$NODE_VERSION-win-x64.zip"
$NodeZipCache = Join-Path $CacheDir $NodeZipName
$NodeDir = Join-Path $ReleaseDir "node"
$AppDir = Join-Path $ReleaseDir "app"
$LauncherCmd = Join-Path $ReleaseDir "feature-recorder.cmd"
$ReadmeSrc = Join-Path $PSScriptRoot "distribution-readme-zh.txt"

function Write-StepBanner {
    param([string]$Title, [string]$Detail = "")
    Write-Host ""
    Write-Host $Title -ForegroundColor Cyan
    if ($Detail) { Write-Host "  $Detail" -ForegroundColor DarkGray }
}

function Download-FileFromMirror {
    param(
        [string]$Url,
        [string]$Dest,
        [string]$Label
    )
    if (Test-Path $Dest) {
        Write-Host "  cache hit: $Dest" -ForegroundColor Green
        return
    }
    $parent = Split-Path $Dest -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Write-Host "  downloading $Label ..." -ForegroundColor Yellow
    Write-Host "  $Url" -ForegroundColor DarkGray
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    $sw.Stop()
    Write-Host "  done in $($sw.Elapsed.ToString('mm\:ss'))" -ForegroundColor Green
}

function Install-PortableNodeRuntime {
    $nodeUrl = "$NODE_MIRROR/v$NODE_VERSION/$NodeZipName"
    Download-FileFromMirror -Url $nodeUrl -Dest $NodeZipCache -Label "Node.js $NODE_VERSION"

    if (Test-Path $NodeDir) {
        Remove-Item $NodeDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $NodeDir -Force | Out-Null

    $tempExtract = Join-Path $CacheDir "node-extract-$NODE_VERSION"
    if (Test-Path $tempExtract) {
        Remove-Item $tempExtract -Recurse -Force
    }
    Expand-Archive -Path $NodeZipCache -DestinationPath $tempExtract -Force

    $inner = Join-Path $tempExtract "node-v$NODE_VERSION-win-x64"
    if (-not (Test-Path $inner)) {
        Write-Host "invalid node zip layout" -ForegroundColor Red
        exit 1
    }
    Copy-Item -Path (Join-Path $inner "*") -Destination $NodeDir -Recurse -Force
    Remove-Item $tempExtract -Recurse -Force

    if (-not (Test-Path (Join-Path $NodeDir "node.exe"))) {
        Write-Host "node.exe missing" -ForegroundColor Red
        exit 1
    }
    Write-Host "  portable node: $NodeDir" -ForegroundColor Green
}

function Install-RuntimeNpmDeps {
    Write-Host "  npm install (registry: $NPM_REGISTRY) ..." -ForegroundColor Yellow
    $pkgJson = @{
        name = "feature-recorder-runtime"
        private = $true
        type = "module"
        dependencies = @{
            "@playwright/test" = "1.49.1"
            "playwright-core" = "1.49.1"
            "chromium-bidi" = "^0.6.0"
            "diff" = "^8.0.3"
            "openai" = "^6.21.0"
        }
    } | ConvertTo-Json -Depth 3
    Set-Content -Path (Join-Path $ReleaseDir "package.json") -Value $pkgJson -Encoding UTF8

    $env:npm_config_registry = $NPM_REGISTRY
    Push-Location $ReleaseDir
    try {
        & npm install --omit=dev --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            Write-Host "npm install failed" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
}

function Install-ChromeWin64 {
    param([string]$DestRoot)

    $chromeExe = Join-Path (Join-Path $DestRoot "chrome-win64") "chrome.exe"
    if (Test-Path $chromeExe) {
        Write-Host "  chrome-win64 already present" -ForegroundColor Green
        return $true
    }

    $localChromeZipPath = if ($env:LOCAL_CHROME_ZIP) { $env:LOCAL_CHROME_ZIP } else { "D:\chrome_download\chrome-win64.zip" }
    if (Test-Path $localChromeZipPath) {
        Write-Host "  local zip: $localChromeZipPath" -ForegroundColor Green
        Expand-Archive -Path $localChromeZipPath -DestinationPath $DestRoot -Force
        if (Test-Path $chromeExe) { return $true }
        Write-Host "invalid local Chromium zip" -ForegroundColor Red
        exit 1
    }

    $zipName = "chrome-win64-$CHROME_CFT_VERSION.zip"
    $zipCache = Join-Path $CacheDir $zipName
    $zipUrl = "$CHROME_MIRROR/$CHROME_CFT_VERSION/win64/chrome-win64.zip"
    Download-FileFromMirror -Url $zipUrl -Dest $zipCache -Label "chrome-win64 $CHROME_CFT_VERSION"

    $tempExtract = Join-Path $CacheDir "chrome-extract-$CHROME_CFT_VERSION"
    if (Test-Path $tempExtract) { Remove-Item $tempExtract -Recurse -Force }
    Expand-Archive -Path $zipCache -DestinationPath $tempExtract -Force

    $inner = Join-Path $tempExtract "chrome-win64"
    if (-not (Test-Path $inner)) {
        Write-Host "unexpected chrome zip layout" -ForegroundColor Red
        exit 1
    }
    Copy-Item -Path $inner -Destination (Join-Path $DestRoot "chrome-win64") -Recurse -Force
    Remove-Item $tempExtract -Recurse -Force

    if (-not (Test-Path $chromeExe)) {
        Write-Host "chrome.exe missing after extract" -ForegroundColor Red
        exit 1
    }
    Write-Host "  chrome-win64: $(Join-Path $DestRoot 'chrome-win64')" -ForegroundColor Green
    return $true
}

function Write-LauncherScript {
    $content = @'
@echo off
setlocal EnableExtensions
title Feature Recorder Dashboard
chcp 65001 >nul 2>&1
set "ROOT=%~dp0"
set "LOG=%ROOT%startup.log"
cd /d "%ROOT%" || goto :fail_cd
set "NODE_EXE=%ROOT%node\node.exe"
set "APP_BUNDLE=%ROOT%app\app.bundle.cjs"
if not exist "%NODE_EXE%" goto :fail_node
if not exist "%APP_BUNDLE%" goto :fail_bundle
netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 goto :fail_port
set "APP_MODE=dashboard"
set "PATH=%ROOT%node;%PATH%"
echo.
echo ========================================
echo   Feature Recorder Dashboard starting...
echo   Browser: http://localhost:3000
echo   Keep this window open.
echo ========================================
echo.
echo [%date% %time%] start >> "%LOG%"
"%NODE_EXE%" "%APP_BUNDLE%" 2>> "%LOG%"
if errorlevel 1 goto :fail_run
goto :eof
:fail_cd
echo [ERROR] Cannot cd to %ROOT%
pause
exit /b 1
:fail_node
echo.
echo [ERROR] node.exe not found. Extract the full zip first.
echo Right-click zip - Extract All - e.g. C:\feature-recorder
echo Expected: %NODE_EXE%
echo.
pause
exit /b 1
:fail_bundle
echo [ERROR] app\app.bundle.cjs not found. Re-extract the full zip.
pause
exit /b 1
:fail_port
echo.
echo [ERROR] Port 3000 is in use. Close the previous recorder window.
echo.
pause
exit /b 1
:fail_run
echo [%date% %time%] failed >> "%LOG%"
echo.
echo [ERROR] Startup failed. See log: %LOG%
type "%LOG%"
echo.
pause
exit /b 1
'@
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($LauncherCmd, $content, $utf8NoBom)
    Write-Host "  launcher: $LauncherCmd" -ForegroundColor Green
}

# [1/5]
if ($SkipClean) {
    Write-StepBanner "[1/5] Clean old artifacts" "SkipClean"
} else {
    Write-StepBanner "[1/5] Clean old artifacts"
}
if (-not $SkipClean) {
    if (Test-Path (Join-Path $ProjectRoot "dist")) {
        Remove-Item (Join-Path $ProjectRoot "dist") -Recurse -Force
    }
    if (Test-Path $ReleaseDir) {
        Remove-Item $ReleaseDir -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null

# [2/5]
Write-StepBanner "[2/5] Build bundle"
npm run build:bundle
$bundleFile = Join-Path (Join-Path $ProjectRoot "dist") "app.bundle.cjs"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $bundleFile)) {
    Write-Host "Build bundle failed." -ForegroundColor Red
    exit 1
}

# [3/5] portable Node via npmmirror
Write-StepBanner "[3/5] Portable Node runtime" "mirror: npmmirror.com (~1-3 min)"
Install-PortableNodeRuntime
Copy-Item -Path $bundleFile -Destination (Join-Path $AppDir "app.bundle.cjs") -Force
Install-RuntimeNpmDeps
Write-LauncherScript

if ($SkipChromium) {
    Write-Host ""
    Write-Host "[4/5][5/5] skipped Chromium (-SkipChromium)" -ForegroundColor Yellow
    Write-Host "run: $LauncherCmd" -ForegroundColor Green
    exit 0
}

# [4/5]
Write-StepBanner "[4/5] Prepare offline Chromium" "mirror: npmmirror chrome-for-testing"
$usingLocalChromeZip = Install-ChromeWin64 -DestRoot $ReleaseDir

# [5/5]
Write-StepBanner "[5/5] Copy static assets"
Copy-Item -Path (Join-Path (Join-Path (Join-Path $ProjectRoot "src") "dashboard") "static") -Destination (Join-Path $ReleaseDir "static") -Recurse -Force
if (Test-Path $ReadmeSrc) {
    Copy-Item -Path $ReadmeSrc -Destination (Join-Path $ReleaseDir "使用说明.txt") -Force
}

Write-Host ""
Write-Host "Build done." -ForegroundColor Green
Write-Host "  launcher: $LauncherCmd" -ForegroundColor Yellow
Write-Host "  includes chrome-win64/" -ForegroundColor DarkGray
