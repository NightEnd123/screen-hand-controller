# Build the Microsoft Store package: dist\AirCursor-<version>.msix (unsigned; the Store signs it).
# Needs: the app built first (build.ps1 -> dist\AirCursor) and the Windows SDK (makeappx, makepri).
# GitHub's Windows build machines have the SDK; .github/workflows/store.yml runs this there.
#   .\packaging\msix\build_msix.ps1 -Version 0.2.0
param([Parameter(Mandatory = $true)][string]$Version)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

$app = "dist\AirCursor"
if (-not (Test-Path "$app\AirCursor.exe")) { throw "$app\AirCursor.exe missing: run build.ps1 first" }

# Store versions are a.b.c.0 (the last part must be 0)
$v = $Version.TrimStart("v")
$parts = $v.Split(".")
while ($parts.Count -lt 3) { $parts += "0" }
$msixVersion = "$($parts[0]).$($parts[1]).$($parts[2]).0"

$store = Get-Content "$PSScriptRoot\store.json" -Raw | ConvertFrom-Json
if ($store.identity_name -like "REPLACE*" -or $store.publisher -like "*REPLACE*") {
    Write-Warning "packaging\msix\store.json still has placeholder values. This package builds and validates, but the Store won't accept it until you copy in your Product identity from Partner Center."
}

# find the SDK tools (newest version)
$kits = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
$sdkBin = Get-ChildItem $kits -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path "$($_.FullName)\x64\makeappx.exe" } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdkBin) { throw "Windows SDK not found (makeappx.exe). Install the Windows SDK, or let GitHub build it (store.yml)." }
$makeappx = "$($sdkBin.FullName)\x64\makeappx.exe"
$makepri = "$($sdkBin.FullName)\x64\makepri.exe"

# layout: the app in AirCursor\, icons in Assets\, the manifest at the top
$layout = "build\msix\layout"
if (Test-Path "build\msix") { Remove-Item -Recurse -Force "build\msix" }
New-Item -ItemType Directory -Force $layout | Out-Null
Copy-Item -Recurse $app "$layout\AirCursor"
Copy-Item -Recurse "$PSScriptRoot\Assets" "$layout\Assets"
# plain names too (scale-100), for anything that doesn't go through resources.pri
foreach ($n in "Square150x150Logo", "Square44x44Logo", "Wide310x150Logo", "StoreLogo") {
    Copy-Item "$layout\Assets\$n.scale-100.png" "$layout\Assets\$n.png"
}
$manifest = Get-Content "$PSScriptRoot\AppxManifest.xml" -Raw
$manifest = $manifest.Replace("{{IDENTITY_NAME}}", $store.identity_name).Replace("{{PUBLISHER}}", $store.publisher)
$manifest = $manifest.Replace("{{PUBLISHER_DISPLAY_NAME}}", $store.publisher_display_name).Replace("{{DISPLAY_NAME}}", $store.display_name)
$manifest = $manifest.Replace("{{VERSION}}", $msixVersion)
[IO.File]::WriteAllText("$root\$layout\AppxManifest.xml", $manifest, (New-Object Text.UTF8Encoding $false))

# resources.pri lets Windows pick the right icon size for each screen
Push-Location "build\msix"
& $makepri createconfig /cf priconfig.xml /dq en-US /o | Out-Null
& $makepri new /pr layout /cf priconfig.xml /mn layout\AppxManifest.xml /of layout\resources.pri /o
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "makepri failed" }
Pop-Location

$out = "dist\AirCursor-$v.msix"
if (Test-Path $out) { Remove-Item $out }
& $makeappx pack /d $layout /p $out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx failed (see messages above)" }
Write-Host "Built $out (version $msixVersion). Upload it in Partner Center > your app > Packages."
