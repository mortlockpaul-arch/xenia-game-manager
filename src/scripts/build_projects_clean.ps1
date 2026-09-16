param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [string]$Folder,

    [switch]$Game
)

if ($Game) {
    if ([string]::IsNullOrWhiteSpace($Folder)) {
        throw "The -Folder parameter is required when -Game is specified."
    }

    if ([System.IO.Path]::IsPathRooted($Folder)) {
        $targetDirectory = $Folder
    }
    else {
        $targetDirectory = Join-Path -Path $Root -ChildPath $Folder
    }
}
else {
    $targetDirectory = $Root
}

if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) {
    throw "Directory does not exist: $targetDirectory"
}

Write-Host "Cleaning: $targetDirectory"

$cleanDirectories = @(
    Get-ChildItem -LiteralPath $targetDirectory -Directory -Recurse -Force |
        Where-Object { $_.Name -in @("bin", "obj") }
)

$fileCount = 0
$bytesSaved = 0

$cleanDirectories = @(
    Get-ChildItem -LiteralPath $targetDirectory -Directory -Recurse -Force |
        Where-Object { $_.Name -in @("bin", "obj") }
)

foreach ($cleanDirectory in $cleanDirectories) {
    $path = $cleanDirectory.FullName

    Write-Host "Removing: $path"

    $files = @(Get-ChildItem -LiteralPath $path -File -Recurse -Force)
    $count = $files.Count
    $size = ($files | Measure-Object -Property Length -Sum).Sum

    try {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop

        $fileCount += $count
        $bytesSaved += $size
    }
    catch {
        Write-Host "Unable to delete '$path': $($_.Exception.Message)"
    }
}

$spaceSaved = if ($bytesSaved -ge 1GB) {
    "{0:N2} GB" -f ($bytesSaved / 1GB)
}
elseif ($bytesSaved -ge 1MB) {
    "{0:N2} MB" -f ($bytesSaved / 1MB)
}
elseif ($bytesSaved -ge 1KB) {
    "{0:N2} KB" -f ($bytesSaved / 1KB)
}
else {
    "$bytesSaved bytes"
}

Write-Host "Clean complete. Removed $fileCount files, saving $spaceSaved."