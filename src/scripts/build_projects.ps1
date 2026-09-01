param(
    [Parameter(Mandatory = $true)]
    [string]$Folder
)

Set-Location "C:\source\Indie-Games\indie-game-archive\"

$Directory = Join-Path (Get-Location) $Folder

$Projects = Get-ChildItem -Path $Directory -Filter "*.csproj" -File

foreach ($Project in $Projects) {
    Write-Host ""
    Write-Host "========================================"
    Write-Host "Building: $($Project.FullName)"
    Write-Host "========================================"

    Remove-Item -Recurse -Force (Join-Path $Project.DirectoryName "obj") -ErrorAction SilentlyContinue

    dotnet restore $Project.FullName
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    dotnet build $Project.FullName
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}