Set-Location "C:\source\Indie-Games\"

Get-ChildItem "." -Directory -Filter "obj" -Recurse |
    Remove-Item -Recurse -Force

Get-ChildItem "." -Directory -Filter "bin" -Recurse |
    Remove-Item -Recurse -Force