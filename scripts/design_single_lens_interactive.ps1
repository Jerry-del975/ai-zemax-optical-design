param(
    [string]$ZosRoot = "D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00",
    [string]$OutDir = "C:\tmp\zemax-single-lens-design",
    [double]$FNumber = 4.0,
    [double]$FieldDeg = 5.0
)

$ErrorActionPreference = "Stop"

function Add-ZosAssemblies($Root) {
    Add-Type -Path (Join-Path $Root "ZOSAPI_NetHelper.dll")
    [ZOSAPI_NetHelper.ZOSAPI_Initializer]::Initialize($Root) | Out-Null
    Add-Type -Path (Join-Path $Root "ZOSAPI_Interfaces.dll")
    Add-Type -Path (Join-Path $Root "ZOSAPI.dll")
}

function Write-JsonLine($Path, $Object) {
    $Object | ConvertTo-Json -Depth 8 -Compress | Add-Content -LiteralPath $Path -Encoding UTF8
}

function Try-Set($Target, [string]$Name, $Value) {
    try {
        $Target.$Name = $Value | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Export-Analysis($System, [string]$Factory, [string]$Name, [string]$Dir) {
    if (-not ($System.Analyses.PSObject.Methods.Name -contains $Factory)) {
        return @{ name = $Name; status = "missing_factory"; file = $null }
    }
    $analysis = $System.Analyses.$Factory.Invoke()
    try {
        $analysis.ApplyAndWaitForCompletion() | Out-Null
        $file = Join-Path $Dir "$Name.txt"
        $analysis.GetResults().GetTextFile($file) | Out-Null
        return @{ name = $Name; status = "exported"; file = $file }
    } catch {
        return @{ name = $Name; status = "error"; error = $_.Exception.Message; file = $null }
    } finally {
        try { $analysis.Close() } catch {}
    }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$analysisDir = Join-Path $OutDir "analyses"
New-Item -ItemType Directory -Force -Path $analysisDir | Out-Null
$logPath = Join-Path $OutDir "design-log.jsonl"

Add-ZosAssemblies $ZosRoot
$connection = New-Object ZOSAPI.ZOSAPI_Connection
$app = $connection.ConnectAsExtension(0)
if ($null -eq $app) { throw "ConnectAsExtension(0) failed. Start Programming > Interactive Extension in OpticStudio." }
if (-not $app.IsValidLicenseForAPI) { throw "Connected, but IsValidLicenseForAPI is false." }
if ($null -eq $app.PrimarySystem) { throw "Connected, but PrimarySystem is null." }

$system = $app.PrimarySystem
$system.New($false) | Out-Null

$logStart = @{
    time = (Get-Date).ToString("s")
    event = "single_lens_design_start"
    f_number = $FNumber
    field_deg = $FieldDeg
}
Write-JsonLine $logPath $logStart

# System data: keep assignments defensive because API enum names vary by release/localization.
$apertureSet = Try-Set $system.SystemData.Aperture "ApertureValue" $FNumber

$wls = $system.SystemData.Wavelengths
while ($wls.NumberOfWavelengths -gt 1) { $wls.RemoveWavelength($wls.NumberOfWavelengths) | Out-Null }
$wls.GetWavelength(1).Wavelength = 0.588
$wls.GetWavelength(1).Weight = 1.0
$wls.AddWavelength(0.486, 1.0) | Out-Null
$wls.AddWavelength(0.656, 1.0) | Out-Null

$fields = $system.SystemData.Fields
while ($fields.NumberOfFields -gt 1) { $fields.RemoveField($fields.NumberOfFields) | Out-Null }
$f1 = $fields.GetField(1)
$f1.X = 0.0; $f1.Y = 0.0; $f1.Weight = 1.0
$fields.AddField(0.0, $FieldDeg, 1.0) | Out-Null

$lde = $system.LDE
while ($lde.NumberOfSurfaces -lt 4) {
    $lde.InsertNewSurfaceAt([Math]::Max(1, $lde.NumberOfSurfaces)) | Out-Null
}

# Minimal plano-convex-ish N-BK7 singlet starter.
$object = $lde.GetSurfaceAt(0)
$stop = $lde.GetSurfaceAt(1)
$front = $lde.GetSurfaceAt(2)
$back = $lde.GetSurfaceAt(3)
$image = $lde.GetSurfaceAt($lde.NumberOfSurfaces - 1)

$stop.Thickness = 0.0
$front.Radius = 50.0
$front.Thickness = 5.0
$front.Material = "N-BK7"
$back.Radius = -50.0
$back.Thickness = 45.0
$back.Material = ""

try { $front.RadiusCell.MakeSolveVariable() | Out-Null } catch {}
try { $back.RadiusCell.MakeSolveVariable() | Out-Null } catch {}
try { $back.ThicknessCell.MakeSolveVariable() | Out-Null } catch {}

$beforePath = Join-Path $OutDir "single-lens-before-optimization.zmx"
$system.SaveAs($beforePath) | Out-Null

$optimizationStatus = "not_run"
try {
    $opt = $system.Tools.OpenLocalOptimization()
    try {
        $opt.RunAndWaitForCompletion() | Out-Null
        $optimizationStatus = "completed"
    } finally {
        try { $opt.Close() } catch {}
    }
} catch {
    $optimizationStatus = "error: $($_.Exception.Message)"
}

$afterPath = Join-Path $OutDir "single-lens-after-optimization.zmx"
$system.SaveAs($afterPath) | Out-Null

$analysisResults = @()
$analysisResults += @(Export-Analysis $system "New_StandardSpot" "spot" $analysisDir)
$analysisResults += @(Export-Analysis $system "New_FftMtf" "mtf" $analysisDir)
$analysisResults += @(Export-Analysis $system "New_RayFan" "rayfan" $analysisDir)
$analysisResults += @(Export-Analysis $system "New_FieldCurvatureAndDistortion" "distortion" $analysisDir)

$summary = @{
    time = (Get-Date).ToString("s")
    event = "single_lens_design_finish"
    aperture_set = $apertureSet
    before_lens = $beforePath
    after_lens = $afterPath
    optimization_status = $optimizationStatus
    analyses = $analysisResults
}
Write-JsonLine $logPath $summary
$summary | ConvertTo-Json -Depth 8
