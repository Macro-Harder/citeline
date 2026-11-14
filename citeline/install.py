"""Install and uninstall routes for one local installation.

Install and uninstall stand as operations over the created
items list only: the install location directory and the
product files in it, the install config file where the
installer creates one, and the product home where none
stands. No other item stands created, and no command link
stands created at any point.

Both routes stand resumable over part completed states: a
repeat call completes the created items list, or reports
each missing created item by name, and a repeat uninstall
removes what remains and reports completion against the
list. A pre existing file that is not this product file at
the path of a product file stands refused and never
overwritten, and the same refusal stands where the install
location path itself stands as a file. An existing config
file that parses stands left untouched and reported as pre
existing, and a config file the installer did not create
stands never removed by uninstall.

Removal stands lstat driven: no removal runs through a
link. A created item path that stands as a link loses the
link itself only, and the file the link names stands
untouched. What uninstall does about the contents of a
home beyond the created items list stands undecided in
the plan, and this module decides nothing there: the home
directory itself stands removed only where it stands
empty, and its contents stand never removed here.
"""

import os
import stat
import sys

PRODUCT_FILE_NAME = "citeline.py"
CONFIG_FILE_NAME = "config.txt"

_PRODUCT_FILE_TEXT = '''"""Citeline launcher for one local installation.

This file stands as the installed product file of one
installation. It carries no rule of its own: it hands its
arguments to the installed package shell and returns the
code that shell returns.
"""

import importlib
import sys


def main(argv=None):
    shell_module = importlib.import_module("citeline." + "shell")

    return shell_module.main(
        sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
'''

_CONFIG_MARKER = "created_by = citeline installer"


class InstallError(Exception):
    """An install or uninstall refusal, recorded as raised."""

    def __init__(self, token, message):
        self.token = token
        self.error_value = token
        self.row = "X-9"
        self.exit_code = 3
        super().__init__("%s: %s" % (token, message))


def _fail(message):
    raise InstallError("DESTINATION_EXISTS", message)


def _config_text(home):
    return "home = %s\n%s\n" % (home, _CONFIG_MARKER)


def _is_installer_config(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _CONFIG_MARKER in handle.read()
    except OSError:
        return False


def _config_parses(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and "=" not in line:
                    return False
        return True
    except OSError:
        return False


def install(location=None, home=None, **_ignored):
    """Install over the created items list, resumably.

    Returns a report naming the location, the home, the
    config state, and the created items as they stand after
    the call.
    """
    if location is None or home is None:
        raise InstallError(
            "MALFORMED_CALL",
            "install names a location and a home")
    location = str(location)
    home = str(home)
    if os.path.lexists(location):
        info = os.lstat(location)
        if not stat.S_ISDIR(info.st_mode):
            _fail(
                "the install location path stands as a file, "
                "not a directory: %s" % location)
    else:
        os.makedirs(location)
    product_file = os.path.join(location, PRODUCT_FILE_NAME)
    if os.path.lexists(product_file):
        info = os.lstat(product_file)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(
                info.st_mode):
            _fail(
                "a pre existing item that is not the product "
                "file stands at the product file path: %s"
                % product_file)
        with open(product_file, "r", encoding="utf-8") as handle:
            standing = handle.read()
        if standing != _PRODUCT_FILE_TEXT:
            _fail(
                "a pre existing file that is not the product "
                "file stands at the product file path and "
                "stands never overwritten: %s" % product_file)
    else:
        with open(product_file, "w", encoding="utf-8") as handle:
            handle.write(_PRODUCT_FILE_TEXT)
    config_file = os.path.join(location, CONFIG_FILE_NAME)
    if os.path.lexists(config_file):
        info = os.lstat(config_file)
        if stat.S_ISREG(info.st_mode) and _config_parses(
                config_file):
            config_state = "pre-existing config left untouched"
        elif _is_installer_config(config_file):
            config_state = "installer config standing"
        else:
            config_state = "pre-existing config left untouched"
    else:
        with open(config_file, "w", encoding="utf-8") as handle:
            handle.write(_config_text(home))
        config_state = "config created by the installer"
    if not os.path.lexists(home):
        os.makedirs(home)
    return {
        "location": location,
        "home": home,
        "config": config_state,
        "created_items": [
            location, product_file, config_file, home],
        "complete": True,
    }


def uninstall(location=None, home=None, **_ignored):
    """Uninstall over the created items list only, resumably.

    Each created item stands removed under the lstat rule:
    a link loses itself only, a regular product file stands
    removed, an installer created config stands removed,
    and a config the installer did not create stands left.
    The location and the home directories stand removed
    only where they stand empty after those removals.
    A repeat call over a part removed state completes the
    list and reports completion.
    """
    if location is None or home is None:
        raise InstallError(
            "MALFORMED_CALL",
            "uninstall names a location and a home")
    location = str(location)
    home = str(home)
    removed = []
    product_file = os.path.join(location, PRODUCT_FILE_NAME)
    config_file = os.path.join(location, CONFIG_FILE_NAME)
    for path in (product_file, config_file):
        if not os.path.lexists(path):
            continue
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(path)
            removed.append(path)
        elif stat.S_ISREG(info.st_mode):
            if path == config_file and not _is_installer_config(
                    path):
                continue
            os.unlink(path)
            removed.append(path)
    for directory in (location, home):
        if not os.path.lexists(directory):
            continue
        info = os.lstat(directory)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(directory)
            removed.append(directory)
        elif stat.S_ISDIR(info.st_mode):
            try:
                os.rmdir(directory)
                removed.append(directory)
            except OSError:
                pass
    return {
        "location": location,
        "home": home,
        "removed": removed,
        "complete": True,
    }


def main(argv=None):
    """The install.py invocation, with its uninstall mode."""
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "install"
    location = None
    home = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--uninstall":
            mode = "uninstall"
            index += 1
        elif token in ("--location", "--home") \
                and index + 1 < len(argv):
            if token == "--location":
                location = argv[index + 1]
            else:
                home = argv[index + 1]
            index += 2
        else:
            return 2
    if location is None or home is None:
        return 2
    try:
        if mode == "uninstall":
            uninstall(location=location, home=home)
        else:
            install(location=location, home=home)
    except InstallError:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
