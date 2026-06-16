# 在 feature_recorder 目录内也可执行
$Root = Split-Path $PSScriptRoot -Parent
& (Join-Path $Root "scripts" "build_feature_recorder.ps1") @args
