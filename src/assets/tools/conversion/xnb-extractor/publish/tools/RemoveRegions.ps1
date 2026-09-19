param(
	[Parameter(Mandatory=$false, Position=0, ValueFromPipeline=$true)]
	[string[]]$Paths = @()
)

if (-not $Paths -or $Paths.Count -eq 0) {
	Write-Host "Usage: .\RemoveRegions.ps1 <file1> [file2 ...]`nExample: .\RemoveRegions.ps1 .\Content\ContentReaders\fna\ListReader.cs"
	exit 1
}

foreach ($p in $Paths) {
	$path = Resolve-Path $p -ErrorAction SilentlyContinue
	if (-not $path) { Write-Host "Not found: $p"; continue }

	$raw = Get-Content -Path $path -Raw -ErrorAction Stop
	$lines = $raw -split "`r?`n"
	$filtered = $lines | Where-Object {
		-not ($_ -match '^\s*#\s*region\b') -and -not ($_ -match '^\s*#\s*endregion\b')
	}
	# Preserve CRLF line endings
	$out = ($filtered -join "`r`n")
	Set-Content -Path $path -Value $out -Encoding UTF8
	Write-Host "Removed region directives from $path"
}