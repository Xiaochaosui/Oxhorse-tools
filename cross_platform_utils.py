"""
Cross-Platform Adapter Module
==============================
Provides unified interface for OS-specific operations.

Supported systems: Linux (primary), Windows (secondary), macOS / others (graceful degrade).

Usage::
    from cross_platform_utils import type_text, mouse_click, send_notification, get_active_window

Linux dependencies:
    sudo apt install xdotool libnotify-bin

Windows dependencies:
    pip install pyautogui  (no extra deps needed for notifications)

NOTE —— Linux xdotool type 需要目标窗口处于焦点状态，调用方应确保窗口已激活。
NOTE —— Windows 下如果 send_notification 遇到权限问题，建议以管理员身份运行。
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess

_SYSTEM = platform.system()

# ── Logging ──────────────────────────────────────────────────────────────────
_log = logging.getLogger(__name__)


def is_linux() -> bool:
    return _SYSTEM == 'Linux'

def is_windows() -> bool:
    return _SYSTEM == 'Windows'


# ── Keyboard Typing ─────────────────────────────────────────────────────────

def type_text(text: str) -> None:
    """Simulate keyboard typing of *text*.

    **Linux**: calls ``xdotool type``.  The target window **MUST** have focus —
    the caller is responsible for activating the window before calling this.

    **Windows**: uses ``pyautogui.write()``.
    """
    if is_linux():
        subprocess.run(['xdotool', 'type', text], check=False)
    elif is_windows():
        try:
            import pyautogui
            pyautogui.write(text)
        except Exception:
            _log.exception("pyautogui.write failed")
    else:
        _log.info("[cross_platform] type_text: %s", text)


# ── Mouse Click ─────────────────────────────────────────────────────────────

def mouse_click(x: int, y: int) -> None:
    """Move the mouse cursor to *(x, y)* and perform a left-click.

    **Linux**: ``xdotool mousemove <x> <y> click 1``.
    **Windows**: ``pyautogui.click(x, y)``.
    """
    if is_linux():
        subprocess.run(
            ['xdotool', 'mousemove', str(x), str(y), 'click', '1'],
            check=False,
        )
    elif is_windows():
        try:
            import pyautogui
            pyautogui.click(x, y)
        except Exception:
            _log.exception("pyautogui.click failed")
    else:
        _log.info("[cross_platform] mouse_click: (%d, %d)", x, y)


# ── Desktop Notification ────────────────────────────────────────────────────

def _windows_toast(title: str, body: str, duration_ms: int) -> None:
    """Show a Windows notification using PowerShell + WinRT toasts.

    Falls back to ``System.Windows.Forms.NotifyIcon`` balloon tip on older
    Windows versions where the WinRT API isn't available.
    """
    # Prefer native WinRT toasts (Win 10+) — they look modern and land in
    # Action Centre.  Fall back to the classic balloon tip on older systems.
    ps_script = f'''\
$title = [System.Environment]::GetEnvironmentVariable('_OXHORSE_TITLE')
$body  = [System.Environment]::GetEnvironmentVariable('_OXHORSE_BODY')
$dur   = [int][System.Environment]::GetEnvironmentVariable('_OXHORSE_DUR')

# -- native WinRT toast (Windows 10+) --
try {{
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $tpl.SelectSingleNode('//text[@id="1"]').InnerText = $title
    $tpl.SelectSingleNode('//text[@id="2"]').InnerText = $body
    $nfr = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
        'Oxhorse Tools')
    $nfr.Show([Windows.UI.Notifications.ToastNotification]::new($tpl))
}} catch {{
    # -- fallback: classic balloon tip --
    [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
    $ni = New-Object System.Windows.Forms.NotifyIcon
    $ni.Icon = [System.Drawing.SystemIcons]::Information
    $ni.BalloonTipTitle  = $title
    $ni.BalloonTipText   = $body
    $ni.Visible = $true
    $ni.ShowBalloonTip($dur * 1000)
    Start-Sleep -Milliseconds ([Math]::Max($dur * 1000 + 1000, 6000))
    $ni.Dispose()
}}
'''
    subprocess.Popen(
        ['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={
            **os.environ,
            '_OXHORSE_TITLE': title,
            '_OXHORSE_BODY': body,
            '_OXHORSE_DUR': str(int(duration_ms / 1000)),
        },
    )


def send_notification(title: str, body: str, duration_ms: int = 5000) -> None:
    """Pop a desktop notification.

    **Linux**: ``notify-send`` via ``subprocess``.
    **Windows**: PowerShell WinRT toast (or balloon-tip fallback).

    Parameters:
        title: Notification title.
        body: Notification body text.
        duration_ms: How long the notification stays on screen (milliseconds).
                     Windows rounds to seconds.
    """
    if is_linux():
        try:
            subprocess.Popen(
                ['notify-send', '-i', 'dialog-information',
                 '-t', str(duration_ms), title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            _log.exception("notify-send failed")
    elif is_windows():
        try:
            _windows_toast(title, body, duration_ms)
        except Exception:
            _log.exception("_windows_toast failed")
    else:
        _log.info("[cross_platform] Notification: [%s] %s", title, body)


# ── Active Window ───────────────────────────────────────────────────────────

def get_active_window() -> tuple[str, str]:
    """Return ``(app_name, window_title)`` of the current foreground window.

    **Linux**: ``xdotool`` + ``ps`` (thread-safe, pure ``subprocess``).
    **Windows**: Win32 API via ``ctypes`` (``GetForegroundWindow`` +
    ``GetModuleBaseNameW``).
    **Other**: Returns ``("", "")``.
    """
    if is_linux():
        return _get_active_window_linux()
    elif is_windows():
        return _get_active_window_windows()
    else:
        return "", ""


def _get_active_window_linux() -> tuple[str, str]:
    try:
        wid = subprocess.check_output(
            ['xdotool', 'getactivewindow'],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        title = subprocess.check_output(
            ['xdotool', 'getwindowname', wid],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        pid = subprocess.check_output(
            ['xdotool', 'getwindowpid', wid],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        app = subprocess.check_output(
            ['ps', '-p', pid, '-o', 'comm='],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return app, title
    except Exception:
        _log.exception("get_active_window (Linux) failed")
        return "", ""


def _get_active_window_windows() -> tuple[str, str]:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        # ── Get foreground window handle ──
        hwnd = user32.GetForegroundWindow()

        # ── Window title ──
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value

        # ── Process name ──
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # PROCESS_QUERY_INFORMATION (0x0400) | PROCESS_VM_READ (0x0010)
        process_handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if process_handle:
            exe_buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(process_handle, None, exe_buf, 260)
            app = exe_buf.value
            kernel32.CloseHandle(process_handle)
        else:
            app = ""

        return app, title
    except Exception:
        _log.exception("get_active_window (Windows) failed")
        return "", ""
