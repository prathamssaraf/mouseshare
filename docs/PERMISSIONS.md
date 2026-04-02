# OS Permissions Setup Guide

## macOS — Accessibility Permission (required)

MouseShare uses macOS's Accessibility API to capture and inject global mouse
and keyboard events. This permission must be granted **once** per machine.

### Steps

1. Open **System Settings** (Apple menu → System Settings)
2. Click **Privacy & Security** in the sidebar
3. Scroll down and click **Accessibility**
4. Click the **+** button
5. Navigate to and select:
   - If running from Terminal: `/Applications/Utilities/Terminal.app`
   - If running the packaged app: `MouseShare.app`
   - If running directly with Python: your Python interpreter
     (e.g. `/usr/local/bin/python3`)
6. Make sure the toggle next to the app is **ON** (blue)
7. Restart MouseShare

### Verify it worked

Run this in Terminal:
```bash
osascript -e 'tell application "System Events" to get name of every process'
```
If it returns a list of process names without an error, the permission is granted.

### Why is this required?

macOS restricts all apps from reading global keyboard/mouse events by default
(since macOS Mojave 10.14). This is a security feature to prevent keyloggers.
MouseShare only uses this permission to forward your own input to your own
other machine — no data leaves your local network.

---

## Windows 10 — Firewall

MouseShare opens a TCP port (default 24800) to accept connections.
Windows Firewall will prompt on first run.

### Steps

1. Run MouseShare for the first time
2. A Windows Security Alert dialog will appear asking about network access
3. Check **Private networks** (your home/office WiFi)
4. Click **Allow access**

### Manual firewall rule (if the prompt doesn't appear)

Open PowerShell as Administrator and run:
```powershell
New-NetFirewallRule `
  -DisplayName "MouseShare" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 24800 `
  -Action Allow
```

### Antivirus note

Some antivirus software flags global keyboard hooks as suspicious.
This is a false positive — pynput's `SetWindowsHookEx` is the same
mechanism used by accessibility software.

If your AV blocks MouseShare:
- Add the MouseShare executable to your AV's exclusion list, OR
- Build from source so your AV can inspect the code

---

## Finding your Mac's IP address

On Mac, run:
```bash
ipconfig getifaddr en0       # WiFi
ipconfig getifaddr en1       # Ethernet (some Macs)
```

Or: System Settings → Wi-Fi → click your network name → IP address field.

This is the IP you enter as `--host` on the Windows client.
