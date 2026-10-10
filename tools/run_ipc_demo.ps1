param(
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$SourceBoard = Join-Path $Root "astra-bldc-demo-start.kicad_pcb"
$PlaybackBoard = Join-Path $Root "astra-bldc-playback.kicad_pcb"
$StatusFile = Join-Path $Root ".astra-demo-status"
$ErrorFile = Join-Path $Root ".astra-demo-error"

function Find-Pcbnew {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\pcbnew.exe",
        "$env:LOCALAPPDATA\Programs\KiCad\9.0\bin\pcbnew.exe",
        "$env:ProgramFiles\KiCad\10.0\bin\pcbnew.exe",
        "$env:ProgramFiles\KiCad\9.0\bin\pcbnew.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Install-KiCad {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw "Install KiCad 9 or newer before running the demo." }
    & $winget.Source install --exact --id KiCad.KiCad --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "KiCad installation failed." }
    $result = Find-Pcbnew
    if (-not $result) { throw "KiCad installed, but pcbnew.exe was not found." }
    return $result
}

function Enable-ApiServer([string]$PcbnewPath) {
    $version = Split-Path -Leaf (Split-Path -Parent (Split-Path -Parent $PcbnewPath))
    $configRoot = Join-Path $env:APPDATA "kicad\$version"
    $commonConfig = Join-Path $configRoot "kicad_common.json"
    $footprintTable = Join-Path $configRoot "fp-lib-table"
    New-Item -ItemType Directory -Path $configRoot -Force | Out-Null
    if (Test-Path $commonConfig) {
        $config = Get-Content $commonConfig -Raw | ConvertFrom-Json
        if (-not $config.api) {
            $config | Add-Member -MemberType NoteProperty -Name api -Value ([pscustomobject]@{})
        }
        $config.api.enable_server = $true
        $config | ConvertTo-Json -Depth 100 | Set-Content $commonConfig -Encoding UTF8
    } else {
        '{"api":{"enable_server":true}}' | Set-Content $commonConfig -Encoding UTF8
    }
    if (-not (Test-Path $footprintTable)) {
        "(fp_lib_table`r`n)" | Set-Content $footprintTable -Encoding ASCII
    }
    # Remove the earlier experimental in-process plugin if it was installed.
    Remove-Item (Join-Path $configRoot "scripting\plugins\astra_bldc") -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $SourceBoard)) { throw "Missing $SourceBoard" }
$Pcbnew = Find-Pcbnew
if (-not $Pcbnew) { $Pcbnew = Install-KiCad }
Enable-ApiServer $Pcbnew

python -c "import kipy; from google.protobuf import runtime_version" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing official KiCad IPC bindings..."
    python -m pip install --user kicad-python==0.8.0 protobuf==5.29.6
    if ($LASTEXITCODE -ne 0) { throw "Could not install KiCad IPC bindings." }
}

Copy-Item $SourceBoard $PlaybackBoard -Force
Remove-Item $StatusFile, $ErrorFile -Force -ErrorAction SilentlyContinue

Write-Host "Opening KiCad with its supported IPC API. No mouse or keyboard automation is used."
$process = Start-Process -FilePath $Pcbnew -ArgumentList "`"$PlaybackBoard`"" -PassThru
Start-Sleep -Seconds 3

python (Join-Path $PSScriptRoot "ipc_demo.py")
if ($LASTEXITCODE -ne 0) {
    if (Test-Path $ErrorFile) { throw (Get-Content $ErrorFile -Raw) }
    throw "KiCad IPC playback failed."
}
if ($process.HasExited) { throw "KiCad closed unexpectedly during playback." }
Write-Host "Playback complete. The result is saved as astra-bldc-playback.kicad_pcb."
