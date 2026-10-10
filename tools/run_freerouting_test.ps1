param(
    [int]$MaxPasses = 20,
    [int]$Threads = 8
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$KiCadRoot = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin"
$KiCadPython = Join-Path $KiCadRoot "python.exe"
$KiCadCli = Join-Path $KiCadRoot "kicad-cli.exe"
$Pcbnew = Join-Path $KiCadRoot "pcbnew.exe"
$Java = "C:\Program Files\Eclipse Adoptium\jre-25.0.4.101-hotspot\bin\java.exe"
$FreeroutingDir = Join-Path $PSScriptRoot "freerouting"
$FreeroutingJar = Join-Path $FreeroutingDir "freerouting-2.5.0.jar"
$FreeroutingUrl = "https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar"

$InputBoard = Join-Path $Root "astra-bldc-autoroute-input.kicad_pcb"
$Dsn = Join-Path $Root "astra-bldc-autoroute-input.dsn"
$Ses = Join-Path $Root "astra-bldc-freerouted.ses"
$OutputBoard = Join-Path $Root "astra-bldc-freerouted.kicad_pcb"
$RouterLog = Join-Path $Root "astra-bldc-freerouting.log"
$DrcReport = Join-Path $Root "astra-bldc-freerouted-drc.rpt"

if (-not (Test-Path $KiCadPython)) {
    throw "KiCad 10 is required. Run run-demo.cmd once to install it."
}
if (-not (Test-Path $Java)) {
    Write-Host "Installing the Java 25 runtime required by Freerouting..."
    winget install --exact --id EclipseAdoptium.Temurin.25.JRE --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Java)) {
        throw "Java 25 installation failed."
    }
}
if (-not (Test-Path $FreeroutingJar)) {
    New-Item -ItemType Directory -Path $FreeroutingDir -Force | Out-Null
    Write-Host "Downloading Freerouting 2.5.0..."
    Invoke-WebRequest -Uri $FreeroutingUrl -OutFile $FreeroutingJar
}
if (-not (Test-Path $InputBoard)) {
    python (Join-Path $PSScriptRoot "generate_project.py")
    if ($LASTEXITCODE -ne 0) { throw "Could not generate the autorouter input board." }
}

Remove-Item $Dsn, $Ses, $OutputBoard, $RouterLog, $DrcReport -Force -ErrorAction SilentlyContinue

Write-Host "1/4 KiCad: exporting fixed-placement PCB to Specctra DSN..."
& $KiCadPython (Join-Path $PSScriptRoot "specctra_bridge.py") export $InputBoard $Dsn
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Dsn)) { throw "DSN export failed." }

Write-Host "2/4 Freerouting: calculating copper routes..."
& $Java -jar $FreeroutingJar -de $Dsn -do $Ses -mp $MaxPasses -mt $Threads 2>&1 |
    Tee-Object -FilePath $RouterLog
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Ses)) { throw "Freerouting failed." }
# Windows PowerShell's Tee-Object writes UTF-16; normalize the evidence log
# so it renders and diffs normally on GitHub.
$routerLogText = Get-Content $RouterLog -Raw
Set-Content -Path $RouterLog -Value $routerLogText -Encoding UTF8

Write-Host "3/4 KiCad: importing the SES routing session..."
& $KiCadPython (Join-Path $PSScriptRoot "specctra_bridge.py") import $InputBoard $Ses $OutputBoard
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $OutputBoard)) { throw "SES import failed." }

Write-Host "4/4 KiCad: running DRC and opening the routed result..."
& $KiCadCli pcb drc $OutputBoard -o $DrcReport
if ($LASTEXITCODE -ne 0) { throw "KiCad DRC command failed." }

$summary = Select-String -Path $RouterLog -Pattern "Auto-routing stage completed" | Select-Object -Last 1
if ($summary) {
    Write-Host ""
    Write-Host $summary.Line
}
Write-Host "Artifacts:"
Write-Host "  Input:  astra-bldc-autoroute-input.kicad_pcb"
Write-Host "  DSN:    astra-bldc-autoroute-input.dsn"
Write-Host "  SES:    astra-bldc-freerouted.ses"
Write-Host "  Result: astra-bldc-freerouted.kicad_pcb"
Write-Host "  Log:    astra-bldc-freerouting.log"
Write-Host "  DRC:    astra-bldc-freerouted-drc.rpt"

Start-Process -FilePath $Pcbnew -ArgumentList "`"$OutputBoard`""
