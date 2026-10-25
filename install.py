#!/usr/bin/env python3
"""
WPS-Zotero Cross-Platform Installer & Service Manager

Installs or uninstalls WPS-Zotero add-on for WPS Office Writer on Linux and Windows.
Configures autostart service (systemd user service on Linux, Run key on Windows),
registers WPS JSAPI plugins, and verifies proxy health.
"""

import os
import sys
import shutil
import re
import time
import subprocess
from proxy import stop_proxy, is_proxy_healthy, VERSION

# Prevent running as root on POSIX
if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
    print("Error: This add-on cannot be installed as root!", file=sys.stderr)
    print("Please run this installer as a normal user.", file=sys.stderr)
    sys.exit(1)

PKG_PATH = os.path.dirname(os.path.abspath(__file__))
APPNAME = f"wps-zotero_{VERSION}"

# Determine addon directory
if os.name == "posix":
    home = os.path.expanduser("~")
    ADDON_PATH = os.path.join(home, ".local", "share", "Kingsoft", "wps", "jsaddons")
    SYSTEMD_USER_DIR = os.path.join(home, ".config", "systemd", "user")
    SYSTEMD_SERVICE_FILE = os.path.join(SYSTEMD_USER_DIR, "wps-zotero-proxy.service")
    AUTOSTART_DIR = os.path.join(home, ".config", "autostart")
    AUTOSTART_DESKTOP_FILE = os.path.join(AUTOSTART_DIR, "wps-zotero-proxy.desktop")
else:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    ADDON_PATH = os.path.join(appdata, "kingsoft", "wps", "jsaddons")
    SYSTEMD_USER_DIR = ""
    SYSTEMD_SERVICE_FILE = ""
    AUTOSTART_DIR = ""
    AUTOSTART_DESKTOP_FILE = ""

INSTALLED_PLUGIN_DIR = os.path.join(ADDON_PATH, APPNAME)

XML_PATHS = {
    "jsplugins": os.path.join(ADDON_PATH, "jsplugins.xml"),
    "publish": os.path.join(ADDON_PATH, "publish.xml"),
    "authwebsite": os.path.join(ADDON_PATH, "authwebsite.xml"),
}

AUTHADDIN_JSON = os.path.join(ADDON_PATH, "authaddin.json")


def is_systemd_user_available() -> bool:
    if shutil.which("systemctl") is None:
        return False
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-system-running"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        status = res.stdout.strip()
        return res.returncode == 0 or status in (
            "running",
            "degraded",
            "initializing",
            "starting",
        )
    except Exception:
        return False


def install_service_linux(proxy_script: str):
    py_exe = sys.executable or "/usr/bin/python3"
    if is_systemd_user_available():
        os.makedirs(SYSTEMD_USER_DIR, exist_ok=True)
        unit_content = f"""[Unit]
Description=WPS-Zotero HTTP Proxy
After=network.target

[Service]
Type=simple
ExecStart={py_exe} {proxy_script}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""
        with open(SYSTEMD_SERVICE_FILE, "w", encoding="utf-8") as f:
            f.write(unit_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=10)
        subprocess.run(["systemctl", "--user", "daemon-reexec"], check=False, timeout=10)
        subprocess.run(["systemctl", "--user", "enable", "wps-zotero-proxy"], check=False, timeout=10)
        subprocess.run(["systemctl", "--user", "restart", "wps-zotero-proxy"], check=False, timeout=10)
        print("Registered systemd user service wps-zotero-proxy")
    else:
        # Fallback to desktop autostart entry
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=WPS-Zotero HTTP Proxy
Exec={py_exe} {proxy_script}
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
"""
        with open(AUTOSTART_DESKTOP_FILE, "w", encoding="utf-8") as f:
            f.write(desktop_content)
        # Detached launch
        subprocess.Popen([py_exe, proxy_script], start_new_session=True)
        print("Registered autostart desktop entry and launched proxy daemon")


def uninstall_service_linux():
    if shutil.which("systemctl"):
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "wps-zotero-proxy"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass
        if os.path.exists(SYSTEMD_SERVICE_FILE):
            try:
                os.remove(SYSTEMD_SERVICE_FILE)
            except OSError:
                pass
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            subprocess.run(
                ["systemctl", "--user", "daemon-reexec"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass
    if os.path.exists(AUTOSTART_DESKTOP_FILE):
        try:
            os.remove(AUTOSTART_DESKTOP_FILE)
        except OSError:
            pass


def find_pythonw() -> str:
    py_dir = os.path.dirname(sys.executable)
    cand = os.path.join(py_dir, "pythonw.exe")
    if os.path.isfile(cand):
        return cand
    which_pyw = shutil.which("pythonw")
    if which_pyw:
        return which_pyw
    return sys.executable


def install_service_windows(proxy_script: str):
    pythonw = find_pythonw()
    cmd = f'"{pythonw}" "{proxy_script}"'
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "WPS-Zotero-Proxy", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        print("Registered Windows Run key for WPS-Zotero-Proxy")
    except Exception as e:
        print(f"Warning: Failed to set Windows Run key: {e}")

    # Immediately launch detached process
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(
            [pythonw, proxy_script],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )
        print("Launched proxy daemon via pythonw")
    except Exception as e:
        print(f"Warning: Failed to launch pythonw: {e}")


def uninstall_service_windows():
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, "WPS-Zotero-Proxy")
            print("Removed Windows Run key for WPS-Zotero-Proxy")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass


def uninstall():
    print("Stopping running proxy daemon if listening...")
    stop_proxy()

    if os.name == "posix":
        uninstall_service_linux()
    else:
        uninstall_service_windows()

    if os.path.isdir(ADDON_PATH):
        for entry in os.listdir(ADDON_PATH):
            full_path = os.path.join(ADDON_PATH, entry)
            if os.path.isdir(full_path) and "wps-zotero" in entry:
                print(f"Removing directory {full_path}")
                shutil.rmtree(full_path, ignore_errors=True)
    if os.path.isfile(AUTHADDIN_JSON):
        try:
            import json
            with open(AUTHADDIN_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            wps_sec = data.get("wps")
            if isinstance(wps_sec, dict):
                namelist = wps_sec.get("namelist")
                if isinstance(namelist, list) and "wps-zotero" in namelist:
                    namelist.remove("wps-zotero")
                    with open(AUTHADDIN_JSON, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                    print("Removed wps-zotero from authaddin.json namelist")
        except Exception as e:
            print(f"Warning: Could not update {AUTHADDIN_JSON}: {e}")

    for fp in XML_PATHS.values():
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            cleaned = re.sub(r"[\ \t]*<[^>]*wps-zotero[^>]*/>\s*\n?", "", content)
            if cleaned != content:
                print(f"Cleaned wps-zotero entries from {fp}")
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(cleaned)
        except Exception as e:
            print(f"Warning: Error updating {fp}: {e}")


def ensure_xml_templates():
    os.makedirs(ADDON_PATH, exist_ok=True)
    if not os.path.exists(XML_PATHS["jsplugins"]):
        with open(XML_PATHS["jsplugins"], "w", encoding="utf-8") as f:
            f.write("<jsplugins>\n</jsplugins>\n")
    if not os.path.exists(XML_PATHS["publish"]):
        with open(XML_PATHS["publish"], "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<jsplugins>\n</jsplugins>\n')
    if not os.path.exists(XML_PATHS["authwebsite"]):
        with open(XML_PATHS["authwebsite"], "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<websites>\n</websites>\n')


def register_xml(fp: str, tagname: str, record: str):
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    close_tag = f"</{tagname}>"
    if close_tag in content:
        idx = content.rfind(close_tag)
        new_content = content[:idx] + f"  {record}\n" + content[idx:]
    else:
        new_content = content + f"\n<{tagname}>\n  {record}\n</{tagname}>\n"
    with open(fp, "w", encoding="utf-8") as f:
        f.write(new_content)


def configure_zotero_windows_prefs():
    if sys.platform != "win32":
        return
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    profiles_dir = os.path.join(appdata, "Zotero", "Zotero", "Profiles")
    if not os.path.isdir(profiles_dir):
        return
    for entry in os.listdir(profiles_dir):
        profile_path = os.path.join(profiles_dir, entry)
        if os.path.isdir(profile_path):
            pref_fn = os.path.join(profile_path, "prefs.js")
            if os.path.isfile(pref_fn):
                try:
                    with open(pref_fn, "r", encoding="utf-8") as f:
                        pref_data = f.read()
                    pref_key = "extensions.zotero.integration.keepAddCitationDialogRaised"
                    if pref_key in pref_data:
                        pref_data = pref_data.replace(
                            f'user_pref("{pref_key}", false);',
                            f'user_pref("{pref_key}", true);',
                        )
                    else:
                        pref_data += f'\nuser_pref("{pref_key}", true);\n'
                    with open(pref_fn, "w", encoding="utf-8") as f:
                        f.write(pref_data)
                    print(f"Configured keepAddCitationDialogRaised in {pref_fn}")
                except Exception as e:
                    print(f"Warning: Could not update {pref_fn}: {e}")


def install():
    print(f"Installing wps-zotero {VERSION}...")
    ensure_xml_templates()

    # Copy files
    print(f"Copying files to {INSTALLED_PLUGIN_DIR}...")
    shutil.copytree(
        PKG_PATH,
        INSTALLED_PLUGIN_DIR,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git*", "__pycache__", "tests", "*.pyc", "*.log"),
    )

    # Register in XML files
    rec_jsplugins = (
        f'<jsplugin name="wps-zotero" type="wps" url="http://127.0.0.1:3889/" version="{VERSION}"/>'
    )
    register_xml(XML_PATHS["jsplugins"], "jsplugins", rec_jsplugins)

    rec_publish = (
        f'<jsplugin url="http://127.0.0.1:3889/" type="wps" enable="enable_dev" install="null" '
        f'version="{VERSION}" name="wps-zotero"/>'
    )
    register_xml(XML_PATHS["publish"], "jsplugins", rec_publish)

    rec_auth = '<website origin="null" name="wps-zotero" status="enable"/>'
    register_xml(XML_PATHS["authwebsite"], "websites", rec_auth)
    if os.path.isfile(AUTHADDIN_JSON):
        try:
            import json
            with open(AUTHADDIN_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            wps_sec = data.get("wps")
            if isinstance(wps_sec, dict):
                namelist = wps_sec.get("namelist")
                if isinstance(namelist, list) and "wps-zotero" not in namelist:
                    namelist.append("wps-zotero")
                    with open(AUTHADDIN_JSON, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                    print("Added wps-zotero to authaddin.json namelist")
        except Exception as e:
            print(f"Warning: Could not update {AUTHADDIN_JSON}: {e}")

    configure_zotero_windows_prefs()

    installed_proxy = os.path.join(INSTALLED_PLUGIN_DIR, "proxy.py")
    if sys.platform == "win32":
        install_service_windows(installed_proxy)
    else:
        install_service_linux(installed_proxy)

    print("Verifying proxy health...")
    healthy = False
    for _ in range(10):
        if is_proxy_healthy():
            healthy = True
            break
        time.sleep(0.5)

    if healthy:
        print("Health check OK")
    else:
        print("Warning: Proxy did not respond to /health check within 5 seconds.")

    print(f"Installation of wps-zotero {VERSION} completed successfully.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "-u":
        print("Uninstalling wps-zotero...")
        uninstall()
        print("Uninstallation complete.")
        return

    # Always perform a clean uninstall first
    print("Performing clean uninstall of previous installations...")
    uninstall()
    install()


if __name__ == "__main__":
    main()
