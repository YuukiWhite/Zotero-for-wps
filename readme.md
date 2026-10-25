# WPS-Zotero

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.txt)
[![Platform: Linux | Windows](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-green.svg)](#installation)
[![Zotero: 6 | 7](https://img.shields.io/badge/Zotero-6%20%7C%207-red.svg)](https://www.zotero.org/)
[![WPS Office](https://img.shields.io/badge/WPS%20Office-Writer-orange.svg)](https://www.wps.com/)

A fast, native WPS Writer integration add-on for [Zotero](https://www.zotero.org/) with full keyboard shortcut support, Microsoft Word cross-compatibility, and automatic background proxy management on both **GNU/Linux** and **Windows**.

---

## Highlights

- ⚡ **Instant Keyboard Shortcuts**: Insert citations (`Alt+Z` or `Ctrl+Alt+C`), insert bibliography (`Alt+B`), and refresh references (`Alt+R`) without touching the mouse.
- 🔄 **Two-Way Microsoft Word Compatibility**: Citations are stored as standard Word-compatible field codes. Send `.docx` files between Linux (WPS Writer) and Windows/macOS (Microsoft Word) seamlessly.
- 🐧 **Native Linux & Windows Support**: Works on modern Linux distributions (Fedora, Ubuntu, Debian, Arch, openSUSE) and Windows 10/11.
- 🛡️ **Zero-Configuration Daemon**: Background HTTP proxy runs quietly as a systemd user service on Linux or autostart background process on Windows.
- ⌨️ **Ribbon Accelerator Keytips**: Intuitive `Alt` &rarr; `Z` &rarr; `<Key>` navigation matching Microsoft Office conventions.

---

## Keyboard Shortcuts & Ribbon Accelerators

### Global Document Shortcuts

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| **`Alt + Z`** | **Add / Edit Citation** | Open Zotero citation dialog at current cursor position |
| **`Ctrl + Alt + C`** | **Add / Edit Citation** | Alternative shortcut (ideal if `Alt+Z` is bound to GPU overlays like GeForce Experience) |
| **`Alt + B`** | **Add / Edit Bibliography** | Insert bibliography at cursor, or update existing references list |
| **`Alt + R`** | **Refresh Citations** | Synchronize all citations and bibliography with your Zotero library |

*Note: Shortcuts are automatically registered when WPS starts and whenever any document is opened or created.*

### Ribbon Keytip Navigation

Press <kbd>Alt</kbd> (or <kbd>F10</kbd>), then press <kbd>Z</kbd> to activate the Zotero ribbon tab, followed by a button key:

| Key Sequence | Command | Description |
| :--- | :--- | :--- |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>C</kbd> | **Add/Edit Citation** | Insert or edit citation |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>B</kbd> | **Add/Edit Refs** | Insert or edit bibliography |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>R</kbd> | **Refresh** | Update all citations |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>P</kbd> | **Preferences** | Change citation style or language |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>N</kbd> | **Add Note** | Insert note from Zotero |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>U</kbd> | **Unlink** | Detach citations into plain text |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>E</kbd> | **Export** | Convert format for switching word processors |
| <kbd>Alt</kbd> &rarr; <kbd>Z</kbd> &rarr; <kbd>A</kbd> | **About** | Show version and license information |

---

## Prerequisites

1. **WPS Office** (WPS Writer with JS Add-in support).
2. **Zotero** (v6 or v7), installed and running in the background.
3. **Python 3** (3.8 or newer):
   - **Linux**: Pre-installed on almost all distributions (`python3 --version`).
   - **Windows**: Download from [python.org](https://www.python.org/downloads/). **Make sure to check "Add Python to PATH"** during installation.

---

## Installation

### Linux

Open your terminal and run:

```bash
# 1. Clone repository
git clone https://github.com/YuukiWhite/Zotero-for-wps.git
cd Zotero-for-wps

# 2. Run installer
python3 install.py
```

The installer will:
- Copy add-on files to `~/.local/share/Kingsoft/wps/jsaddons/wps-zotero_0.2.0/`.
- Register the add-on in WPS configuration files (`jsplugins.xml`, `publish.xml`, `authaddin.json`).
- Set up and start a systemd user service (`wps-zotero-proxy.service`).
- Verify health check on `http://127.0.0.1:21931/health`.

### Windows

Open **Command Prompt** (`cmd`) or **PowerShell** as a normal user:

```cmd
git clone https://github.com/YuukiWhite/Zotero-for-wps.git
cd Zotero-for-wps
python install.py
```

*(Alternatively, you can double-click `windows安装与卸载.bat`)*

The installer will:
- Copy add-on files to `%APPDATA%\kingsoft\wps\jsaddons\wps-zotero_0.2.0`.
- Register the add-on in WPS add-on manifests.
- Configure autostart for the background proxy using `pythonw.exe`.
- Configure Zotero connector preferences if necessary.

---

## Verification

1. Start **Zotero**.
2. Open **WPS Writer**.
3. You will see a new **Zotero** tab on the ribbon.
4. Press `Alt+Z` (or `Ctrl+Alt+C`). The red Zotero citation bar will pop up immediately.
5. Select a reference, press Enter, and the citation will be inserted into your document!

---

## Uninstallation

To cleanly remove the add-on, stop the proxy service, and clean up registry/config entries:

- **Linux**:
  ```bash
  python3 install.py -u
  ```
- **Windows**:
  ```cmd
  python install.py -u
  ```

---

## How It Works

```
┌─────────────────┐        JSA HTTP        ┌────────────────────────┐        Local HTTP       ┌──────────────────┐
│   WPS Writer    │ ─────────────────────> │  Python Proxy Daemon   │ ─────────────────────>  │  Zotero Desktop  │
│ (JS Add-in Tab) │  http://127.0.0.1:21931│  (systemd / autostart) │  http://127.0.0.1:23119 │ (Citing Server)  │
└─────────────────┘                        └────────────────────────┘                         └──────────────────┘
```

1. **WPS JSA Frontend**: Uses WPS Office's JavaScript API (JSA) and Microsoft Word-compatible `Application.KeyBindings` to handle ribbon buttons, accelerator keys, and shortcut events.
2. **Local HTTP Proxy (`proxy.py`)**: Zotero's local HTTP citation API (listening on port 23119) enforces strict CORS and host header restrictions. WPS's embedded browser cannot talk directly to Zotero without triggering security blocks. The lightweight Python proxy runs locally on port 21931, forwarding commands with proper headers (`X-Zotero-Connector-API-Version`, stripping `Origin`/`Sec-Fetch-*`).
3. **Persistence**:
   - Linux: Managed via systemd user unit `wps-zotero-proxy.service` (auto-restarts on failure, runs only in user session).
   - Windows: Managed via `pythonw.exe` and user startup registry.

---

## Microsoft Word Compatibility Guide

- **Field Codes**: Citations created by this add-on use standard Word-compatible field codes.
- **Cross-Platform Editing**: You can write a paper in WPS Writer on Linux, save it as `.docx`, and email it to colleagues using Microsoft Word on Windows or macOS. They can edit or add citations using the official Zotero Word integration seamlessly.
- **Rule of Thumb**: When prompted by Zotero for Document Preferences, always choose **"Store citations as Fields"** (the default in MS Word) rather than Bookmarks.

---

## Troubleshooting & FAQ

### 1. "Zotero is not running" or Error 502
- Ensure the Zotero desktop application is open before clicking citation buttons or using shortcuts.
- Check proxy status on Linux:
  ```bash
  systemctl --user status wps-zotero-proxy
  ```
- Test proxy health:
  ```bash
  curl http://127.0.0.1:21931/health
  # Should return: {"status": "ok", "version": "0.2.0"}
  ```

### 2. `Alt+Z` does not trigger Zotero
- Some graphics drivers (e.g. NVIDIA GeForce Experience in-game overlay or AMD Radeon software) intercept `Alt+Z` globally.
- Use **`Ctrl+Alt+C`** as the built-in alternative shortcut.
- Alternatively, use the ribbon accelerator: press <kbd>Alt</kbd>, then <kbd>Z</kbd>, then <kbd>C</kbd>.

### 3. Zotero citation dialog appears behind WPS Writer
- This is an upstream window manager / focus behavior in certain desktop environments. Click the Zotero icon in your taskbar / dock to bring the red search bar to front.

---

## Running Automated Tests

The repository includes a comprehensive unit test suite covering proxy operations, CORS headers, error handling, ribbon XML schemas, and shortcut keybindings:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

All 13 tests verify proxy forwarding, connection recovery, keycode arithmetic, and XML/JSA syntax.

---

<details>
<summary><b>🇨🇳 中文说明 / Chinese Documentation (点击展开)</b></summary>

### 简介
WPS-Zotero 是为 WPS 文字（WPS Writer）开发的 Zotero 文献引用集成插件，支持 **GNU/Linux** 与 **Windows** 双平台。彻底解决学术科研人员在 Linux 下缺乏好用的论文排版与文献管理工具的问题，并支持与 Microsoft Word 用户无缝协同。

### 快捷键与快速访问
- **`Alt + Z`** 或 **`Ctrl + Alt + C`**：快速插入/编辑文献引用（调用 Zotero 红色搜索栏）。
- **`Alt + B`**：插入或更新参考文献列表（Bibliography）。
- **`Alt + R`**：刷新所有引用与文献库同步。
- **Ribbon 快捷键**：按下 <kbd>Alt</kbd> 后按 <kbd>Z</kbd> 进入 Zotero 选项卡，按 <kbd>C</kbd> 插入引用、<kbd>B</kbd> 插入文献列表、<kbd>R</kbd> 刷新、<kbd>P</kbd> 首选项。

### 一键安装
确保已安装 WPS Office、Zotero（保持后台运行）以及 Python 3。

- **Linux 安装**：
  ```bash
  git clone https://github.com/YuukiWhite/Zotero-for-wps.git
  cd Zotero-for-wps
  python3 install.py
  ```
- **Windows 安装**：
  ```cmd
  git clone https://github.com/YuukiWhite/Zotero-for-wps.git
  cd Zotero-for-wps
  python install.py
  ```
  *(或直接双击 `windows安装与卸载.bat`)*

- **卸载**：
  执行 `python3 install.py -u`（Windows 下执行 `python install.py -u`）。

### 与 Microsoft Word 兼容性
引文以 Word 兼容的域（Field）形式保存为 `.docx`。在 Linux 下用 WPS 撰写的论文，发给使用 Windows / macOS + MS Word 的导师或同行，双方均可直接继续添加或编辑引用。

</details>

---

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.txt).
Based on upstream work by [Tang, Kewei](https://github.com/tankwyn/WPS-Zotero).
