$ErrorActionPreference = "Stop"
$env:MICROMANAGER_PATH = "C:\Program Files\Micro-Manager-2.0"
Set-Location "C:\Users\abc\Documents\GitHub\python-fish-sorter"
uv run python fish_sorter\GUI\fish_picker.py
