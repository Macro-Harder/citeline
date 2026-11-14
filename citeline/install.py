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

# The directory holding the citeline package of this
# shipped tree: the parent of this file's directory. The
# installed launcher names it, so the installed file runs
# from any working directory, and the default install
# location stands beside it.
_PRODUCT_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))


def _product_file_text():
    """The installed product file text for this tree.

    The launcher carries no rule of its own. It takes its
    own directory off the module search path, because a
    file named citeline.py standing in that directory
    shadows the citeline package it must import, and it
    puts the shipped product directory that installed it
    on the path, so the package stands found from any
    working directory. It then hands its arguments to the
    package shell and returns the code that shell returns.
    """
    return '''"""Citeline launcher for one local installation.

This file stands as the installed product file of one
installation. It carries no rule of its own: it hands its
arguments to the installed package shell and returns the
code that shell returns.
"""

import os
import sys

_PACKAGE_PARENT = %r
_OWN_DIR = os.path.dirname(os.path.abspath(__file__))


def _prepare_path():
    kept = []
    for entry in sys.path:
        resolved = os.path.abspath(entry) if entry else None
        if resolved is not None and resolved == _OWN_DIR:
            continue
        kept.append(entry)
    sys.path[:] = kept
    if _PACKAGE_PARENT not in sys.path:
        sys.path.insert(0, _PACKAGE_PARENT)


def main(argv=None):
    _prepare_path()
    import importlib
    shell_module = importlib.import_module("citeline." + "shell")

    return shell_module.main(
        sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
''' % (_PRODUCT_DIR,)


_CONFIG_MARKER = "created_by = citeline installer"

# The row, exit code, and class of each token this module
# raises, as the joined entry 13 table states them. The
# shared error vocabulary carries the same values; this
# table stands so the module also runs as a shipped file
# standing alone, where the package may not stand imported
# yet.
_TOKEN_FORMS = {
    "MALFORMED_CALL": ("U-8", 2, "usage"),
    "CONFIG_INVALID": ("X-1", 5, "integrity"),
    "DESTINATION_EXISTS": ("X-9", 3, "domain"),
}


class InstallError(Exception):
    """An install or uninstall refusal, recorded as raised."""

    def __init__(self, token, message):
        self.token = token
        self.error_value = token
        row, exit_code, precedence = _TOKEN_FORMS.get(
            token, ("X-9", 3, "domain"))
        try:
            from citeline import errors
            entry = errors.error_for_token(token)
            if entry is not None:
                row = entry["row"]
                exit_code = entry["exit_code"]
                precedence = entry["precedence_class"]
        except Exception:
            pass
        self.row = row
        self.exit_code = exit_code
        self.precedence_class = precedence
        super().__init__("%s: %s" % (token, message))


def _fail(message):
    raise InstallError("DESTINATION_EXISTS", message)


def _is_within(path, parent):
    """True where one resolved path stands inside another."""
    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:
        return False


def _check_no_overlap(location):
    """The plan Section 8.3 overlap check, before any write.

    Runs over the two resolved paths, the shipped product
    directory and the requested or defaulted install
    location, and refuses each overlap form with a recorded
    error: the location equal to the product directory, the
    location inside the product directory, and the product
    directory inside the location. No install write stands
    before this check passes.
    """
    product_dir = os.path.realpath(_PRODUCT_DIR)
    resolved = os.path.realpath(location)
    if resolved == product_dir or _is_within(
            resolved, product_dir) or _is_within(
            product_dir, resolved):
        _fail(
            "the install location overlaps the shipped "
            "product directory, and the install stands "
            "refused before any write: %s" % location)


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


# The keys the installer config form itself carries: the
# home key the installer writes into the config it creates,
# and the created_by marker key that names an installer
# config. The journal config parse reports both as unknown,
# because they are not journal config keys; on this surface
# they stand known, so their warnings stand not surfaced.
_INSTALLER_CONFIG_KEYS = ("home", "created_by")


def _surface_warnings(warnings):
    """The parse warnings this surface reports, in parse form.

    A warning the parse formed stands surfaced as it
    stands, naming its key, except a warning naming one of
    the installer config keys above, which this surface
    itself writes and reads.
    """
    surfaced = []
    for warning in warnings:
        text = str(warning)
        key = text.rsplit(":", 1)[-1].strip() \
            if ":" in text else text
        if key in _INSTALLER_CONFIG_KEYS:
            continue
        surfaced.append(text)
    return surfaced


def _config_check(path, home):
    """A pair of validity and the warnings the parse formed.

    The parse is the config parse itself, at journal
    strength: a file that cannot be parsed, holds a value
    of the wrong form, or holds a duplicate key stands
    invalid, on plan config rule 5. An unknown key stands
    valid and stands in the warnings pair, on brief
    Section 3.5 point 5 and plan Section 3.2 rule 4, so
    the caller can report it as a warning instead of the
    warning standing computed and discarded. Where the
    package journal cannot stand imported, the local line
    test above stands as the floor and the duplicate and
    wrong form limbs are checked here in the same terms;
    that floor forms no warnings.
    """
    journal = None
    try:
        if _PRODUCT_DIR not in sys.path:
            sys.path.insert(0, _PRODUCT_DIR)
        from citeline import journal as journal_module
        journal = journal_module
    except Exception:
        journal = None
    if journal is not None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            return False, []
        try:
            _values, warnings = journal.parse_config(
                text, home=str(home))
            return True, _surface_warnings(warnings)
        except Exception:
            return False, []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False, []
    seen = set()
    for line in text.split("\n"):
        if not line or line.startswith("#"):
            continue
        parts = line.split(" = ")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return False, []
        if parts[0] in seen:
            return False, []
        seen.add(parts[0])
    return _config_parses(path), []


def _config_valid(path, home):
    """True where a standing config file parses in full."""
    valid, _warnings = _config_check(path, home)
    return valid


def install(location=None, home=None, **_ignored):
    """Install over the created items list, resumably.

    Returns a report naming the location, the home, the
    config state, and the created items as they stand after
    the call. The report also carries, under warnings, each
    warning the parse of a standing config file formed, in
    parse form naming its key: an unknown key is reported
    as a warning and is not an install failure, on brief
    Section 3.5 point 5, so the call succeeds and the
    warning stands in the report for the caller to print.
    """
    if location is None or home is None:
        raise InstallError(
            "MALFORMED_CALL",
            "install names a location and a home")
    location = str(location)
    home = str(home)
    _check_no_overlap(location)
    created_items = []
    if os.path.lexists(location):
        info = os.lstat(location)
        if not stat.S_ISDIR(info.st_mode):
            _fail(
                "the install location path stands as a file, "
                "not a directory: %s" % location)
    config_file = os.path.join(location, CONFIG_FILE_NAME)
    config_warnings = []
    if os.path.lexists(config_file):
        info = os.lstat(config_file)
        if stat.S_ISREG(info.st_mode):
            valid, config_warnings = _config_check(
                config_file, home)
            if not valid:
                raise InstallError(
                    "CONFIG_INVALID",
                    "an existing config file that is itself "
                    "invalid fails the install, with the file "
                    "still left untouched: %s" % config_file)
    if not os.path.lexists(location):
        os.makedirs(location)
        created_items.append(location)
    product_file = os.path.join(location, PRODUCT_FILE_NAME)
    product_text = _product_file_text()
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
        if standing != product_text:
            _fail(
                "a pre existing file that is not the product "
                "file stands at the product file path and "
                "stands never overwritten: %s" % product_file)
    else:
        with open(product_file, "w", encoding="utf-8") as handle:
            handle.write(product_text)
        created_items.append(product_file)
    if os.path.lexists(config_file):
        info = os.lstat(config_file)
        if stat.S_ISREG(info.st_mode) and _is_installer_config(
                config_file):
            config_state = "installer config standing"
        else:
            config_state = "pre-existing config left untouched"
    else:
        with open(config_file, "w", encoding="utf-8") as handle:
            handle.write(_config_text(home))
        config_state = "config created by the installer"
        created_items.append(config_file)
    if not os.path.lexists(home):
        os.makedirs(home)
        created_items.append(home)
    return {
        "location": location,
        "home": home,
        "config": config_state,
        "warnings": config_warnings,
        "created_items": created_items,
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


def _default_location():
    """The stated default install location.

    Where no argument stands, the install location is the
    directory named citeline beside the shipped product
    directory.
    """
    return os.path.join(os.path.dirname(_PRODUCT_DIR), "citeline")


def _default_home():
    """The stated default product home: a directory named
    .citeline in the operator home directory."""
    return os.path.join(os.path.expanduser("~"), ".citeline")


def main(argv=None):
    """The install.py invocation, with its uninstall mode.

    The stated form: install.py run with the system Python
    from the shipped product directory, with one optional
    argument naming the install location; uninstall is the
    word uninstall as the first argument, with the install
    location as its optional second argument and the same
    default. The flag spellings --location and --home, and
    the --uninstall flag, stand accepted beside the stated
    form. The output stands in the simple form only and
    states the home path.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "install"
    location = None
    home = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "uninstall" and index == 0:
            mode = "uninstall"
            index += 1
        elif token == "--uninstall":
            mode = "uninstall"
            index += 1
        elif token in ("--location", "--home"):
            if index + 1 >= len(argv):
                print("install: MALFORMED_CALL: %s names a value"
                      % token, file=sys.stderr)
                return 2
            if token == "--location":
                location = argv[index + 1]
            else:
                home = argv[index + 1]
            index += 2
        elif not token.startswith("-") and location is None:
            location = token
            index += 1
        else:
            print("install: MALFORMED_CALL: unrecognised "
                  "argument: %s" % token, file=sys.stderr)
            return 2
    if location is None:
        location = _default_location()
    if home is None:
        home = _default_home()
    try:
        if mode == "uninstall":
            report = uninstall(location=location, home=home)
            print("uninstalled")
            print("location: %s" % report["location"])
            print("home: %s" % report["home"])
            for removed in report.get("removed") or []:
                print("removed: %s" % removed)
        else:
            report = install(location=location, home=home)
            print("installed")
            print("location: %s" % report["location"])
            print("home: %s" % report["home"])
            print("config: %s" % report["config"])
            for warning in report.get("warnings") or []:
                print("warning: %s" % warning)
            for created in report.get("created_items") or []:
                print("created: %s" % created)
    except InstallError as exc:
        print("install: %s" % (exc,), file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
