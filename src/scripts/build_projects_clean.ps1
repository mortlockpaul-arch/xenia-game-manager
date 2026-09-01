Get-ChildItem ".\indie-game-archive" -Directory -Filter "obj" -Recurse |
    Remove-Item -Recurse -Force

Get-ChildItem ".\indie-game-archive" -Directory -Filter "bin" -Recurse |
    Remove-Item -Recurse -Force