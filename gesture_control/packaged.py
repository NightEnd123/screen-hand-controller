"""Running as the Microsoft Store (MSIX) app.

A Store app has a "package identity". It keeps its files in its own LocalState folder, and it
starts with Windows through the Store's StartupTask (the Startup-folder shortcut used otherwise
doesn't work for packaged apps). Outside the Store everything here reports "not packaged".
"""
import asyncio
import ctypes
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)
TASK_ID = "GestureControlStartup"      # must match the StartupTask in packaging/msix/AppxManifest.xml
_NO_PACKAGE = 15700                    # APPMODEL_ERROR_NO_PACKAGE


def family_name():
    """The package family name when running as the Store app, else None."""
    try:
        k32 = ctypes.windll.kernel32
        n = ctypes.c_uint32(0)
        if k32.GetCurrentPackageFamilyName(ctypes.byref(n), None) == _NO_PACKAGE:
            return None
        buf = ctypes.create_unicode_buffer(n.value)
        if k32.GetCurrentPackageFamilyName(ctypes.byref(n), buf) != 0:
            return None
        return buf.value
    except Exception:
        return None


def data_dir(pfn):
    """The package's own LocalState folder (a real path, so Notepad can open files in it)."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Packages" / pfn / "LocalState"


def launched_at_startup():
    """True when Windows started the app at login through the StartupTask."""
    try:
        from winrt.windows.applicationmodel import AppInstance
        from winrt.windows.applicationmodel.activation import ActivationKind
        args = AppInstance.get_activated_event_args()
        return args is not None and args.kind == ActivationKind.STARTUP_TASK
    except Exception:
        return False


async def _task():
    from winrt.windows.applicationmodel import StartupTask
    return await StartupTask.get_async(TASK_ID)


def startup_enabled():
    try:
        from winrt.windows.applicationmodel import StartupTaskState
        state = asyncio.run(_task()).state
        return state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    except Exception:
        log.exception("reading the startup task failed")
        return False


def set_startup(on):
    """Turn starting with Windows on or off. Returns the resulting state (True = on).
    If the person turned it off in Task Manager > Startup apps, only they can turn it back on there."""
    async def go():
        from winrt.windows.applicationmodel import StartupTaskState
        task = await _task()
        if on:
            state = await task.request_enable_async()
        else:
            task.disable()
            state = task.state
        if on and state == StartupTaskState.DISABLED_BY_USER:
            log.info("startup task was turned off in Task Manager; it has to be turned back on there")
        return state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    try:
        return asyncio.run(go())
    except Exception:
        log.exception("changing the startup task failed")
        return startup_enabled()
