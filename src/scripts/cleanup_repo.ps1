python .\.venv\Lib\site-packages\git_filter_repo.py `
    --force `
    --path src/downloads `
    --path build_tools/dist `
    --path build `
    --path dist `
    --path .venv `
    --path-glob "*.msi" `
    --path-glob "*.zip" `
    --path-glob "*.7z" `
    --invert-paths

git reflog expire --expire=now --all
git gc --aggressive --prune=now

git push --force --all origin
git push --force --tags origin
