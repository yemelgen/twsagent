#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TWS Agent Installation Script

Copyright 2021-2024 Eugene Yemelyanov <yemelgen@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

# Configuration
APP_NAME = "twsagent"
APP_MAIN = "app/main.py"
APP_TOML = "pyproject.toml"
COMMENT = "TWS Agent - An RPC API server for Interactive Brokers TWS/Gateway"
LICENSE = "LICENSE.txt"
TERMINAL = True
PACKAGE_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1042.01.zip"


# Validate Python version FIRST
import sys

if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9 or higher is required to continue.")

# Now safe to import Python 3.6+
import logging
import os
import subprocess
from pathlib import Path

try:
    import venv
except ImportError:
    raise SystemExit('Python package "venv" is required to continue.')

# Setup logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class InstallationError(Exception):
    """Custom exception for installation errors"""

    pass


def download_file_with_ssl(url: str, destination: Path) -> None:
    """Download a file from a URL with SSL fallback."""

    import ssl
    import urllib.request

    try:
        # Try with default SSL context first
        ssl_context = ssl.create_default_context()
        with urllib.request.urlopen(url, context=ssl_context) as response:
            with open(destination, "wb") as out_file:
                out_file.write(response.read())
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            # Windows often has SSL certificate issues, fall back to unverified
            logger.info(
                "SSL certificate verification failed, using unverified connection..."
            )
            ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=ssl_context) as response:
                with open(destination, "wb") as out_file:
                    out_file.write(response.read())
        else:
            raise


def download_packages(app_dir: Path) -> bool:
    """Download and extract packages required for the application."""

    import shutil
    import tempfile
    import zipfile

    ibapi_dir = app_dir / "ibapi"

    if ibapi_dir.exists() and (ibapi_dir / "__init__.py").exists():
        logger.info("IB API already present, skipping download.")
        return True

    logger.info("IB API not found. Attempting to download...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "ibapi.zip"

            logger.info("Downloading IB API...")
            download_file_with_ssl(PACKAGE_URL, zip_path)

            logger.info("Extracting IB API...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_path)

            extracted_ibapi = temp_path / "IBJts" / "source" / "pythonclient" / "ibapi"

            if not extracted_ibapi.exists():
                raise InstallationError(
                    "Could not find ibapi directory in downloaded archive"
                )

            logger.info(f"Installing IB API to {ibapi_dir}...")
            shutil.copytree(extracted_ibapi, ibapi_dir)

        logger.info("IB API downloaded and installed successfully.")
        return True

    except Exception as e:
        logger.error(f"Failed to download IB API: {e}")
        logger.info(
            "\nPlease download IB API manually:\n"
            "1. Visit: https://interactivebrokers.github.io/\n"
            "2. Download TWS API for your platform\n"
            f"3. Extract and copy 'IBJts/source/pythonclient/ibapi/' to:\n"
            f"   {ibapi_dir}\n"
        )
        return False


def create_shortcut_on_windows(pyexe: Path, pyscript: Path, pydir: Path) -> None:
    """Create Windows shortcut using PowerShell"""

    shortcut = Path("start.lnk")
    launcher = Path("start.cmd")
    exe_dir = pyexe.parent

    if TERMINAL:
        pywexe = exe_dir / "python.exe"
    else:
        pywexe = exe_dir / "pythonw.exe"

    powershell_cmd = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{shortcut}');"
        f"$s.TargetPath = '{pywexe}';"
        f"$s.Arguments = '{pyscript}';"
        f"$s.WorkingDirectory = '{pydir}';"
        "$s.save()"
    )

    try:
        subprocess.run(
            ["powershell", "-Command", powershell_cmd],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise InstallationError(f"Failed to create Windows shortcut: {e.stderr}")

    with launcher.open("w") as fd:
        fd.write(f"@echo off\nchcp 65001\ncd %~dp0\n{pyexe} {pyscript}\npause")


def create_shortcut_on_linux(pyexe: Path, pyscript: Path, pydir: Path) -> None:
    """Create Linux XDG desktop shortcut"""

    shortcut = Path("start.desktop")
    launcher = Path("start.sh")

    desktop_content = (
        f"#!{pyexe} {pyscript}\n"
        "[Desktop Entry]\n"
        "Version=1.0\n"
        f"Name={APP_NAME}\n"
        "Comment=Python3 Application\n"
        f"Path={pydir}\n"
        f"Exec={pyexe} {pyscript}\n"
        "Icon=/usr/share/pixmaps/python3.xpm\n"
        f"Terminal={'true' if TERMINAL else 'false'}\n"
        "Type=Application\n"
        "Categories=Application;"
    )

    with shortcut.open("w") as fd:
        fd.write(desktop_content)
    shortcut.chmod(0o755)

    with launcher.open("w") as fd:
        fd.write(f"#!/usr/bin/env bash\ncd {pydir}\n{pyexe} {pyscript}")
    launcher.chmod(0o755)


def create_shortcut_on_mac(pyexe: Path, pyscript: Path, pydir: Path) -> None:
    """Create application launcher for macOS"""

    shortcut = Path("start.app")
    launcher = Path("start.command")
    iconfile = (
        "/System/Library/Frameworks/Python.Framework"
        "/Resources/Python.app/Contents"
        "/Resources/PythonInterpreter.icns"
    )

    contents_dir = shortcut / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    icon_link = resources_dir / "launcher.icns"
    if not icon_link.exists():
        icon_link.symlink_to(iconfile)

    with launcher.open("w") as fd:
        fd.write(f"#!/usr/bin/env bash\ncd {pydir}\n{pyexe} {pyscript}")
    launcher.chmod(0o755)

    plist_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>CFBundleName</key>\n"
        f"  <string>{APP_NAME}</string>\n"
        "  <key>CFBundleDisplayName</key>\n"
        f"  <string>{APP_NAME}</string>\n"
        "  <key>CFBundleIconFile</key>\n"
        "  <string>launcher.icns</string>\n"
        "  <key>CFBundlePackageType</key>\n"
        "  <string>APPL</string>\n"
        "  <key>CFBundleExecutable</key>\n"
        "  <string>launcher.sh</string>\n"
        "</dict>\n"
        "</plist>"
    )

    with (contents_dir / "Info.plist").open("w") as fd:
        fd.write(plist_content)

    launcher_sh = macos_dir / "launcher.sh"
    with launcher_sh.open("w") as fd:
        if TERMINAL:
            fd.write(f"#!/usr/bin/env bash\nopen -a terminal {launcher.resolve()}")
        else:
            fd.write(f"#!/usr/bin/env bash\ncd {pydir}\n{pyexe} {pyscript}")
    launcher_sh.chmod(0o755)


def add_shortcut_to_menu() -> None:
    """Add shortcut to system menu"""

    if sys.platform == "linux":
        menu = Path.home() / ".local/share/applications"
        filename = f"{APP_NAME}.desktop"
        source = Path("start.desktop")
    elif sys.platform == "win32":
        menu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
        filename = f"{APP_NAME}.lnk"
        source = Path("start.lnk")
    elif sys.platform == "darwin":
        menu = Path("/Applications")
        filename = f"{APP_NAME}.app"
        source = Path("start.app")
    else:
        raise InstallationError(f"Unsupported platform: {sys.platform}")

    menu.mkdir(parents=True, exist_ok=True)
    destination = menu / filename

    if source.exists():
        source.rename(destination)
        logger.info(f"Shortcut added to {destination}")
    else:
        raise InstallationError(f"Shortcut file {source} not found")


def confirm_license(license_file: Path) -> bool:
    """Display license and get user confirmation"""

    print(COMMENT)
    print("-" * len(COMMENT))
    print(license_file.read_text())
    reply = input(
        "Please enter 'Yes' to confirm your agreement to the terms above (Yes/No): "
    )
    return reply.lower() in ["y", "yes", "ye"]


def confirm_menu_shortcut() -> bool:
    """Ask user if they want to add shortcut to menu"""

    reply = input("Do you wish to add a shortcut to desktop menu? (Yes/No): ")
    return reply.lower() in ["y", "yes", "ye"]


class ExtendedEnvBuilder(venv.EnvBuilder):
    """Extended EnvBuilder with package installation and shortcut creation"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def post_setup(self, context):
        """Hook for post-setup tasks"""

        pass

    def install_packages(self, context):
        """Install packages from pyproject.toml"""

        os.environ["VIRTUAL_ENV"] = str(context.env_dir)

        try:
            subprocess.run(
                [
                    str(context.env_exe),
                    "-u",  # Unbuffered output
                    "-m",
                    "pip",
                    "--log",
                    "install.log",
                    "install",
                    "--quiet",  # Suppress verbose output
                    "-e",
                    ".",  # Install production dependencies only
                    "-f",
                    "dist",
                ],
                check=True,
                capture_output=True,
                text=True,
                bufsize=1,  # Line buffering
            )
        except subprocess.CalledProcessError as e:
            raise InstallationError(
                f"Failed to install packages. Check install.log for details.\n"
                f"Error: {e.stderr}"
            )

    def create_shortcuts(self, context):
        """Create platform-specific shortcuts"""

        if sys.platform == "linux":
            create_shortcut_on_linux(
                Path(context.env_exe),
                Path(context.app_main),
                Path(context.app_dir),
            )
        elif sys.platform == "win32":
            create_shortcut_on_windows(
                Path(context.env_exe),
                Path(context.app_main),
                Path(context.app_dir),
            )
        elif sys.platform == "darwin":
            create_shortcut_on_mac(
                Path(context.env_exe),
                Path(context.app_main),
                Path(context.app_dir),
            )

    def create(
        self, env_dir: Path, app_dir: Path, app_main: Path, app_toml: Path
    ) -> bool:
        """Create a virtual environment and install the application"""

        steps = [
            ("Downloading packages", self._step_download_packages),
            ("Creating virtual environment", self._step_create_env),
            ("Setting up Python environment", self._step_setup_python),
            ("Setting up pip", self._step_setup_pip),
            ("Setting up scripts", self._step_setup_scripts),
            ("Installing packages", self._step_install_packages),
            ("Running post-setup", self._step_post_setup),
            ("Creating shortcuts", self._step_create_shortcuts),
        ]

        # Store context
        self._env_dir = env_dir
        self._app_dir = app_dir
        self._app_main = app_main
        self._app_toml = app_toml

        for idx, (description, step_func) in enumerate(steps, start=1):
            print(f"[{idx}] {description}... ", end="", flush=True)
            try:
                step_func()
                print("Done.")
            except Exception as exc:
                print("Failed!")
                logger.error(f"{description} failed: {exc}")
                return False

        return True

    def _step_download_packages(self):
        """Step 1: Download packages if not present"""

        if not download_packages(self._app_dir):
            raise InstallationError("Package download failed. Please install manually.")

    def _step_create_env(self):
        """Step 2: Create environment directories"""

        context = self.ensure_directories(str(self._env_dir))
        context.app_dir = str(self._app_dir)
        context.app_main = str(self._app_main)
        context.app_toml = str(self._app_toml)
        self.create_configuration(context)
        self._context = context

    def _step_setup_python(self):
        """Step 3: Setup Python in virtual environment"""

        self.setup_python(self._context)

    def _step_setup_pip(self):
        """Step 4: Setup pip"""

        self._setup_pip(self._context)

    def _step_setup_scripts(self):
        """Step 5: Setup scripts"""

        if not self.upgrade:
            self.setup_scripts(self._context)

    def _step_install_packages(self):
        """Step 6: Install packages"""

        if not self.upgrade:
            self.install_packages(self._context)

    def _step_post_setup(self):
        """Step 7: Run post-setup"""

        if not self.upgrade:
            self.post_setup(self._context)

    def _step_create_shortcuts(self):
        """Step 8: Create shortcuts"""

        if not self.upgrade:
            self.create_shortcuts(self._context)


def main():
    """Main installation function"""

    use_symlinks = sys.platform != "win32"

    # Application paths
    app_dir = Path(__file__).resolve().parent
    app_license = app_dir / LICENSE
    env_dir = app_dir / "venv"
    app_main = app_dir / APP_MAIN
    app_toml = app_dir / APP_TOML

    if not app_toml.exists():
        logger.error(f"Project configuration file not found: {app_toml}")
        sys.exit(1)

    # Change to application directory
    os.chdir(app_dir)

    # Show license and get confirmation
    if not confirm_license(app_license):
        print("Installation cancelled.")
        sys.exit(0)

    # Create virtual environment and install
    builder = ExtendedEnvBuilder(
        system_site_packages=False,
        symlinks=use_symlinks,
        clear=False,
        upgrade=False,
        with_pip=True,
        prompt=APP_NAME,
    )

    if builder.create(env_dir, app_dir, app_main, app_toml):
        if confirm_menu_shortcut():
            try:
                add_shortcut_to_menu()
            except InstallationError as e:
                logger.error(f"Failed to add menu shortcut: {e}")

        print("\nInstallation has finished successfully.")
        print("Now you can try to run your application.")
    else:
        logger.error("Installation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
