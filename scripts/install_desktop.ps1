# Install shortcuts for this checkout without changing the user's Python or PATH.
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv\Scripts\python.exe'
$pythonwPath = Join-Path $repoPath '.venv\Scripts\pythonw.exe'
$entryPath = Join-Path $PSScriptRoot 'openx_desktop.pyw'
if (-not (Test-Path -LiteralPath $pythonwPath)) { throw 'Create the project .venv first.' }
& $pythonPath -c 'import pystray, fastapi, uvicorn'
if ($LASTEXITCODE -ne 0) { throw 'Install the desktop extra in the project environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $repoPath 'web\dist\index.html'))) { throw 'Build the web interface first: npm ci and npm run build in the web folder.' }
$iconPath = Join-Path $PSScriptRoot 'openx.ico'
& $pythonPath -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "src")); from openx_workbench.launcher import tray_image; tray_image().save(sys.argv[2])' $repoPath $iconPath
if ($LASTEXITCODE -ne 0) { throw 'Could not create the OpenX icon.' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shellObject = New-Object -ComObject WScript.Shell
foreach ($item in @(@{Name='OpenX'; Args=''}, @{Name='OpenX - Stop'; Args=' --stop'})) {
    $shortcutPath = Join-Path $desktopPath ($item.Name + '.lnk')
    $shortcut = $shellObject.CreateShortcut($shortcutPath)
    if ((Test-Path -LiteralPath $shortcutPath) -and $shortcut.TargetPath -ne $pythonwPath) {
        throw "An unrelated shortcut already exists: $shortcutPath"
    }
    $shortcut.TargetPath = $pythonwPath
    $shortcut.Arguments = '"' + $entryPath + '"' + $item.Args
    $shortcut.WorkingDirectory = $repoPath
    $shortcut.IconLocation = $iconPath
    $shortcut.Description = if ($item.Args) { 'Stop OpenX and its preview workers' } else { 'Start OpenX and open the workbench' }
    $shortcut.Save()
    Write-Output $shortcutPath
}
