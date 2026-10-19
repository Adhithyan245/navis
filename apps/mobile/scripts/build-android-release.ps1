<#
  Builds the signed Play Store bundle (.aab) for Navis.

    cd apps\mobile
    .\scripts\build-android-release.ps1 -AppUrl https://navis-web.onrender.com -AppId com.yourname.navis -VersionCode 1

  -AppUrl       your hosted HTTPS site (required; http:// is refused)
  -AppId        permanent Play package name (can't change after the first upload)
  -VersionCode  must increase with every upload to Play
  -VersionName  shown to users (default "1.0.<VersionCode>")

  Needs: Java 21 + Android SDK in D:\dev-tools (or set JAVA_HOME / ANDROID_HOME),
  and android\keystore.properties pointing at your upload keystore.
  Output: apps\mobile\release\navis-<VersionName>.aab
#>
param(
  [Parameter(Mandatory = $true)][string]$AppUrl,
  [string]$AppId = "app.navis.mobile",
  [int]$VersionCode = 1,
  [string]$VersionName = ""
)
# Native tools write notices to stderr; judge success by exit codes instead.
$ErrorActionPreference = "Continue"
if (-not $AppUrl.StartsWith("https://")) { throw "AppUrl must be https:// for a store build." }
if (-not $VersionName) { $VersionName = "1.0.$VersionCode" }
$mobile = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$mobile\android\keystore.properties")) { throw "android\keystore.properties is missing (upload key)." }

if (-not $env:JAVA_HOME) { $env:JAVA_HOME = (Get-ChildItem D:\dev-tools\jdk -Directory | Select-Object -First 1).FullName }
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = "D:\dev-tools\android-sdk" }
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
if (-not $env:GRADLE_USER_HOME) { $env:GRADLE_USER_HOME = "D:\dev-tools\gradle-home" }
# Works around a JDK loopback-socket issue on some Windows setups.
$env:JAVA_TOOL_OPTIONS = "-Djdk.net.unixdomain.tmpdir=D:\dev-tools\tmp"

Push-Location $mobile
try {
  $env:NAVIS_APP_URL = $AppUrl
  $env:NAVIS_APP_ID = $AppId
  npx cap sync android 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "cap sync failed." }
  Push-Location android
  .\gradlew.bat bundleRelease --no-daemon --console=plain "-PnavisAppId=$AppId" "-PnavisVersionCode=$VersionCode" "-PnavisVersionName=$VersionName" 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Gradle build failed." }
  Pop-Location
  New-Item -ItemType Directory -Force "$mobile\release" | Out-Null
  $out = "$mobile\release\navis-$VersionName.aab"
  Copy-Item "$mobile\android\app\build\outputs\bundle\release\app-release.aab" $out -Force
  Write-Output "Built $out"
} finally {
  Pop-Location
}
