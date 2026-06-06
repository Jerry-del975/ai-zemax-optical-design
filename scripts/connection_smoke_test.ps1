param(
    [string]$ZosRoot = "D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00",
    [switch]$Standalone,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

function Write-Status($Name, $Value) {
    Write-Output ("{0}: {1}" -f $Name, $Value)
}

if (-not (Test-Path -LiteralPath $ZosRoot)) {
    throw "OpticStudio root not found: $ZosRoot"
}

$interfaces = Join-Path $ZosRoot "ZOSAPI_Interfaces.dll"
$zosapi = Join-Path $ZosRoot "ZOSAPI.dll"
$nethelper = Join-Path $ZosRoot "ZOSAPI_NetHelper.dll"

foreach ($dll in @($nethelper, $interfaces, $zosapi)) {
    if (-not (Test-Path -LiteralPath $dll)) {
        throw "Required DLL not found: $dll"
    }
}

Add-Type -Path $nethelper
[ZOSAPI_NetHelper.ZOSAPI_Initializer]::Initialize($ZosRoot) | Out-Null
Add-Type -Path $interfaces
Add-Type -Path $zosapi

Write-Status "ZOS root" $ZosRoot
Write-Status "Mode" ($(if ($Standalone) { "Standalone" } else { "Interactive Extension" }))

$connection = New-Object ZOSAPI.ZOSAPI_Connection
$app = $null

if ($Standalone) {
    Write-Status "Warning" "Standalone can start or crash OpticStudio if the API license/session is not healthy."
    $job = Start-Job -ScriptBlock {
        param($Root)
        Add-Type -Path (Join-Path $Root "ZOSAPI_NetHelper.dll")
        [ZOSAPI_NetHelper.ZOSAPI_Initializer]::Initialize($Root) | Out-Null
        Add-Type -Path (Join-Path $Root "ZOSAPI_Interfaces.dll")
        Add-Type -Path (Join-Path $Root "ZOSAPI.dll")
        $connection = New-Object ZOSAPI.ZOSAPI_Connection
        $app = $connection.CreateNewApplication()
        if ($null -eq $app) {
            return @{ Connected = $false; License = $false; PrimarySystem = $false }
        }
        $result = @{
            Connected = $true
            License = [bool]$app.IsValidLicenseForAPI
            PrimarySystem = [bool]($app.PrimarySystem -ne $null)
        }
        $app.CloseApplication()
        return $result
    } -ArgumentList $ZosRoot

    if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
        Stop-Job $job
        Remove-Job $job
        throw "Standalone CreateNewApplication() did not return within $TimeoutSeconds seconds."
    }

    $result = Receive-Job $job
    Remove-Job $job
    Write-Status "Connected" $result.Connected
    Write-Status "IsValidLicenseForAPI" $result.License
    Write-Status "PrimarySystem" $result.PrimarySystem
    exit $(if ($result.Connected -and $result.License -and $result.PrimarySystem) { 0 } else { 2 })
}

$app = $connection.ConnectAsExtension(0)
Write-Status "Connected" ($null -ne $app)
if ($null -eq $app) {
    exit 2
}

Write-Status "IsValidLicenseForAPI" ([bool]$app.IsValidLicenseForAPI)
Write-Status "PrimarySystem" ([bool]($app.PrimarySystem -ne $null))

if ($app.IsValidLicenseForAPI -and ($app.PrimarySystem -ne $null)) {
    exit 0
}

exit 2
