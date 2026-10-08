# Windows desktop launcher

Double-click **OpenX** on the desktop to start the local service and open the
workbench in your default browser. Reopening the shortcut reuses the running
instance. Startup waits for the service health check before opening the browser.

The launcher starts `openx_workbench.api`, which serves the React workbench from
`web/dist` together with its local API. If the bundle has not been built, the
launcher stops with a message explaining how to build it.

Use **OpenX - Stop** on the desktop, or **关闭 OpenX** in the tray menu, to stop
the service and all preview workers it owns. Closing a browser tab leaves the
service running. The tray also offers open, restart, and a log-folder shortcut.
Windows may put the tray icon in the taskbar overflow menu.

Projects, global asset versions and saved reports remain in the existing local
data directory. Finish saving any edits before stopping or restarting. The
launcher uses a Windows Job Object to own the service tree, so even an abrupt
launcher exit terminates its preview children. It never kills other Python or
esmini processes by executable name, and never closes your browser.

## Install for a development checkout

Install the package with the `desktop` extra in the project's `.venv`
(`python -m pip install ".[desktop]"`), build the web bundle once with
`cd web && npm ci && npm run build`, then run `scripts/install_desktop.ps1`
once. Rebuilding the bundle needs no launcher restart; Python source changes
restart the service on the next open. The script creates the two shortcuts using
the checkout's `pythonw.exe` and generates their icons (the stop shortcut carries a red stop badge). Normal daily use needs no
terminal. No administrator access, PATH change, login startup or Windows service
installation is required.

The shortcuts point to this checkout and its virtual environment. If the checkout
is moved or removed, recreate them from the new checkout. This is a local launcher,
not a standalone distributable executable.

## Diagnostics and scope

Logs live under `%LOCALAPPDATA%/OpenXScenarioWorkbench/launcher`, or under
`OPENX_DATA_DIR/launcher` when overridden. `launcher.log` records lifecycle events;
`web-service.log` contains the service output. Startup failures show a tray notification
and allow retrying from the tray. The launcher selects an available localhost port.
Its separate control endpoint also binds only to localhost and requires a random
per-run token; duplicate shortcuts use it to request open or stop.

The normal `OPENX_ESMINI_PATH`, model configuration and data-directory environment
settings are inherited. Existing esmini path selection in the workbench remains
available. This launcher does not bundle esmini, models, credentials or asset data.

Validation includes real web service start/health/restart/stop, exclusive instance
locking, rejection of unauthenticated control requests, and termination of a real
grandchild process when the owned job closes.
