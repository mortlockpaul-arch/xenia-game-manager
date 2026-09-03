param(
    [Parameter(Mandatory = $true)]
    [string]$Folder
)

$Games = "C:\source\Indie-Games\indie-game-archive"
$Directory = Join-Path $Games $Folder

Write-Host "Cleaning: $Directory"

Set-Location $Directory

Get-ChildItem "." -Directory -Filter "obj" -Recurse |
    Remove-Item -Recurse -Force

Get-ChildItem "." -Directory -Filter "bin" -Recurse |
    Remove-Item -Recurse -Force

Write-Host "Clean complete."