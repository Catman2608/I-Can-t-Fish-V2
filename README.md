# License

This project is licensed under the GNU GPL v3.

You are free to study, modify, and redistribute this software. If you distribute a project containing code from this repository, the resulting project must also be released under the GPL v3, with its source code made available.

# I Can't Fish V2

Pre-built versions are available for supported platforms on the official releases page:

[Official Downloads / Releases](https://drive.google.com/drive/u/0/folders/1ETQHjVVasL2fMUIkd_MX41J-azLVmlas)

If a pre-built version is not available for your system, follow the source installation guide below.

# Project Environment Setup Guide

## 📋 Overview

This guide walks through setting up Python and all required modules for running the project. The application uses GUI automation, OCR, screen capture, and cross-platform OS features.

---

## 1️⃣ Prerequisites

- **OS**:
  - Windows (fully supported)
  - macOS (fully supported)
  - Linux (not supported as mouse clicks won't register)
- **Administrator/Root access** may be needed for certain system-level operations
- **Internet connection** for downloading packages

---

## 2️⃣ Install Python

### Option A: Using the Official Installer (Recommended)
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download and run the installer
3. ✅ **Important**: Check *"Add Python to PATH"* during installation

### Option B: Using Homebrew (macOS only)
```bash
# Install via official website, or with homebrew if using a script:
python -m ensurepip --upgrade  # pip may not be installed by default on macOS
```

### Verify Installation
Open Terminal/Command Prompt and run:
```bash
python --version
# or
python3 --version
```
Expected output: `Python 3.8+`

---

## 3️⃣ Install Required Modules

Run this command in order to download the required libraries:

```bash
pip install numpy mss pynput requests opencv-python
```
If the command above fails, try using pip3 instead:
```bash
pip3 install numpy mss pynput requests opencv-python
```

### Complete Package List Reference
| Module | Command | Purpose |
|--------|---------|---------|
| `numpy` | `pip install numpy` | Numerical operations, image arrays |
| `mss` | `pip install mss` | Screenshot capture (multi-screen support) |
| `pynput` | `pip install pynput` | Keyboard/mouse automation & listening |
| `requests` | `pip install requests` | Discord API calls |
| `opencv-python` or `opencv-python-headless` | `pip install opencv-python` | Image processing (cv2) |

---

## 4️⃣ Verify Installation

Create a test script `test_imports.py`:

```python
import json, os, re, time, sys
from tkinter import messagebox

from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController, Button

import cv2, numpy as np, mss
if sys.platform == "win32":
    import ctypes, wintypes

elif sys.platform == "darwin":
    from Quartz import NSScreen

elif sys.platform.startswith("linux"):
    from Xlib import X, XK, display as Xdisplay

import requests, io

print("✅ All modules imported successfully!")
```

Run it with `python test_imports.py` — no errors means your setup is complete.

---

## 5️⃣ Troubleshooting Quick Fixes

| Error | Solution |
|-------|----------|
| `_tkinter.TclError: No such file or directory` | Install tkinter: `pip install tkinter` (macOS) or reinstall Python with "Add to PATH" checked |
| `M1 Mac — OpenCV error about libGL` | Use `opencv-python-headless` instead of regular opencv |
| Permission denied on screenshot/capture | Run the script as Administrator (Windows) or with elevated privileges (macOS) |
