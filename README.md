> **AI disclaimer:** This project — including its code, architecture, icon,
> and this README — was written by Claude (Anthropic's AI assistant) working
> with the repository owner. Review the code yourself before trusting it with
> real credentials or production hosts.

# Pascal Simple SSH

A powerful SSH/SFTP client for Windows with a Qt GUI, true-color/256-color
terminal emulation, and SSH keepalive support.

## Features

- **Free-form address bar** — type `host`, `user@host`, `user@host:port`,
  `ssh://user@host:port`, or `[ipv6]:port` and hit Enter to connect. A
  dropdown remembers your last 20 connections.
- **Tabbed sessions** — open multiple connections at once.
- **Terminal emulation** — built on [pyte](https://github.com/selectel/pyte),
  rendered with QPainter; supports 16-color, 256-color and 24-bit truecolor
  (SGR 38/48;2/5), bold/italic/underline/strikethrough/reverse, scrollback
  (mouse wheel, Shift+PageUp/PageDown), text selection (Ctrl+Shift+C to copy,
  Ctrl+Shift+V / Shift+Insert to paste), and copying a screenshot of just the
  terminal to the clipboard (right-click → Copy Screenshot, or View menu).
- **SFTP panel** — optional right-hand file browser over the same connection:
  navigate, upload, download, rename, delete, create folders, and edit a
  remote file directly in an external editor of your choice (auto-uploads on
  save).
- **SSH tunnels** — local (`-L`) and remote (`-R`) port forwarding, managed
  per-tab from the Tunnels menu.
- **Custom commands** — save named command snippets and send them to the
  active session from the Commands menu.
- **Host key verification** — checks against `~/.ssh/known_hosts`, prompting
  on first use and warning loudly if a host key changes.
- **Authentication** — SSH agent / default key files first, falls back to an
  interactive password prompt.
- **Keepalive** — sends SSH-level keepalive packets to hold connections open;
  can be disabled or retuned in Settings > Preferences.
- **Bookmarks** — save connections (host/user/port/key file) and optionally
  save the password too, stored securely in Windows Credential Manager (never
  in plain text) via [keyring](https://github.com/jaraco/keyring).
- **Themes** — System or a flat Gray palette (Settings > Preferences).

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

```
.venv\Scripts\python -m psssh
```

## Build a standalone .exe

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller psssh.spec
```

The one-folder build is written to `dist\PascalSimpleSSH\PascalSimpleSSH.exe`.

## Project layout

```
psssh/
  connection.py       host-string parsing
  settings.py          QSettings-backed preferences (theme, keepalive, fonts, ...)
  bookmarks.py          JSON-backed saved connections
  secrets_store.py        keyring-backed bookmark password storage
  commands.py              JSON-backed saved command snippets
  tunnel.py                 local/remote SSH port forwarding
  host_keys.py                known_hosts verification + GUI prompts
  ssh_worker.py                 paramiko session thread (auth, PTY, keepalive)
  sftp_worker.py                  paramiko SFTP job-queue thread
  terminal_widget.py                pyte + QPainter terminal emulator
  sftp_panel.py                       remote file browser widget
  session_widget.py                     terminal + SFTP panel for one connection
  main_window.py                          tabs, menus, address bar, status bar
  theme.py                                   System / Gray palette switching
  icon.py                                      app icon lookup
  dialogs/                                       Preferences, Bookmarks, Tunnels, Commands
  assets/icon.ico                                  app icon
  app.py                                             QApplication entry point
psssh.spec            PyInstaller build spec
```
