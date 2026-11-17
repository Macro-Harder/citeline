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
list. Upgrade stands on the install route: running the
installer of a newer tree over a standing installation
upgrades that installation in place, replacing the
launcher and refreshing the package copy from the
installing tree, and no manual deletion stands between
the old installation and the new one. A pre existing file that is not this product file at
the path of a product file stands refused and never
overwritten, and the same refusal stands where the install
location path itself stands as a file. An existing config
file that parses stands left untouched and reported as pre
existing, and a config file the installer did not create
stands never removed by uninstall.

Removal stands lstat driven: no removal runs through a
link. A created item path that stands as a link loses the
link itself only, and the file the link names stands
untouched. The home the installer created stands removed
with everything in it, journal contents included, as the
brief and the README promise: uninstall removes
everything the installer created, so no imported answer
survives undisclosed and no reinstall resurrects the old
history.
"""

import os
import shutil
import stat
import sys

PRODUCT_FILE_NAME = "citeline.py"
# The config file at the install location is the governing
# config file of the installation, as brief Section 3.5
# point 5 states: config values are read from that file at
# run start, and the journal config reading reads it for
# the home its home key names (Step 19 item R19-049). The
# config.txt a home may also carry states values for its
# own runs beside it, under the journal reading's stated
# precedence.
CONFIG_FILE_NAME = "config.txt"
PACKAGE_DIR_NAME = "citeline"

# The directory holding the citeline package of this
# shipped tree: the parent of this file's directory. The
# installed launcher names it, so the installed file runs
# from any working directory, and the default install
# location stands beside it.
_PRODUCT_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))


def _product_file_text():
    """The installed product file text for this tree.

    The launcher carries no rule of its own. The install
    stands self contained: the installer copies the citeline
    package into the install location beside this file, and
    the launcher puts its own directory on the module search
    path, so the package copy in the install location stands
    found from any working directory, independent of the
    tree that built the install. It then hands its arguments
    to the package shell and returns the code that shell
    returns. Where that package copy cannot be loaded, the
    installation stands broken: the launcher reports a
    recorded Citeline error at a designed exit code, never
    a raw traceback at exit 1.
    """
    return '''"""Citeline launcher for one local installation.

This file stands as the installed product file of one
installation. It carries no rule of its own: it hands its
arguments to the installed package shell and returns the
code that shell returns.
"""

import os
import sys

_OWN_DIR = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_PARENT = _OWN_DIR


def _prepare_path():
    if _PACKAGE_PARENT not in sys.path:
        sys.path.insert(0, _PACKAGE_PARENT)


def main(argv=None):
    _prepare_path()
    import importlib
    try:
        shell_module = importlib.import_module(
            "citeline." + "shell")
    except Exception as exc:
        print(
            "citeline: DESTINATION_EXISTS: the installed "
            "product package cannot be loaded from this "
            "install location, so the installation stands "
            "broken and nothing was run: %s"
            % type(exc).__name__, file=sys.stderr)
        return 3
    return shell_module.main(
        sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
'''


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


def _restrict(path, mode):
    """Set an owner only permission on a product file or
    directory the product created or keeps, so protection
    is set by the product itself and never left to whatever
    the process umask gives. A link at the path is never
    followed for this."""
    try:
        info = os.lstat(path)
    except OSError:
        return
    if stat.S_ISLNK(info.st_mode):
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _create_file_exclusive(path, text, home=None):
    """Create one installer file by the pinned B4 write
    sequence (plan EC-18 subsection 8.1, decisions
    D-KF-18-PICK and D-KF-18-TEMP): a complete temporary
    file in the destination directory, flushed to storage;
    a hard link from the temporary name to the destination
    name, which fails where the destination exists, so a
    link or file planted at the path after the existence
    checks and before this create is refused by the link
    step itself and never followed or replaced; the
    destination directory flushed; and the temporary name
    unlinked. An interrupted create leaves no partial file
    at the named path, and a platform that cannot perform
    a step of the sequence fails the install closed on
    row X-12."""
    directory = os.path.dirname(os.path.abspath(path))
    destination_name = os.path.basename(path)
    _remove_orphaned_temporaries(directory, destination_name)
    temporary_path = os.path.join(
        directory,
        "%s.tmp-%d-%d" % (destination_name,
                          _last_journal_sequence(home),
                          os.getpid()))
    fd = os.open(temporary_path,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary_path, path)
    except FileExistsError:
        raise
    except OSError:
        raise InstallError(
            "LOCK_UNAVAILABLE",
            "the platform cannot perform the hard link "
            "step of the pinned write sequence, so the "
            "install fails closed and no file stands at "
            "the named path: %s" % path)
    try:
        _flush_directory(directory)
    except OSError:
        for standing in (path, temporary_path):
            try:
                os.unlink(standing)
            except OSError:
                pass
        raise InstallError(
            "LOCK_UNAVAILABLE",
            "the platform cannot perform the directory "
            "flush step of the pinned write sequence, so "
            "the install fails closed and no file stands "
            "at the named path: %s" % path)
    try:
        os.unlink(temporary_path)
    except OSError:
        raise InstallError(
            "LOCK_UNAVAILABLE",
            "the platform cannot perform the temporary "
            "unlink step of the pinned write sequence, "
            "so the install fails closed: %s" % path)


def _temporary_process_number(name, destination_name):
    """The process number a B4 temporary name carries, or
    None where the name is not a temporary of the
    destination, on the parse form decision D-KF-18-TEMP
    states: the destination name, the suffix .tmp-, the
    journal sequence digit run, a hyphen separator, and
    the process number digit run at the end of the name."""
    prefix = destination_name + ".tmp-"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    sequence, separator, process = rest.partition("-")
    if not separator or not sequence.isdigit() \
            or not process.isdigit():
        return None
    return int(process)


def _remove_orphaned_temporaries(directory, destination_name):
    """Remove the orphaned B4 temporaries of one
    destination standing in its directory, before this
    invocation writes (decision D-KF-18-TEMP): an orphan
    is a file matching the temporary naming pattern that
    this invocation did not create and whose process
    number names no live process. A temporary whose
    process stands live stands left standing, whatever
    invocation created it."""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        process = _temporary_process_number(
            name, destination_name)
        if process is None:
            continue
        try:
            os.kill(process, 0)
        except ProcessLookupError:
            pass
        except OSError:
            continue
        else:
            continue
        try:
            os.unlink(os.path.join(directory, name))
        except OSError:
            pass


def _flush_directory(directory):
    """Flush one directory to storage, the directory
    flush step of the pinned B4 write sequence."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _last_journal_sequence(home):
    """The sequence of the journal's last entry as this
    invocation reads it, or 0 over a home whose journal
    stands empty or absent (decision D-KF-18-TEMP, the
    form for a writing invocation that appends no entry,
    as the install writes do not)."""
    if not home:
        return 0
    try:
        path = os.path.join(str(home), "journal.jsonl")
        count = 0
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
        return count
    except Exception:
        return 0


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


def _config_fault_detail(path):
    """The cause, the rule broken, and the line at fault
    for a config file that does not parse, in the three
    causes the brief distinguishes at CL19-164: a line
    that cannot be parsed, a value of the wrong form, and
    a duplicate key. Returns a short statement naming all
    three, or a general statement where no line fault of
    those forms stands found."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return "cause: the file cannot be read"
    limit_keys = ()
    try:
        if _PRODUCT_DIR not in sys.path:
            sys.path.insert(0, _PRODUCT_DIR)
        from citeline import journal as journal_module
        limit_keys = tuple(
            getattr(journal_module, "_LIMIT_DEFAULT", {}) or {})
    except Exception:
        limit_keys = ()
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    seen = set()
    for number, line in enumerate(lines, 1):
        if line == "" or line.startswith("#"):
            continue
        if line != line.strip() or "\t" in line or "\r" in line:
            return (
                "cause: the line cannot be parsed (rule: "
                "one key, one space, an equals sign, one "
                "space, and the value per line), at line %d"
                % number)
        parts = line.split(" = ")
        if len(parts) != 2 or not parts[0] or not parts[1] \
                or " " in parts[0] or "=" in parts[0]:
            return (
                "cause: the line cannot be parsed (rule: "
                "one key, one space, an equals sign, one "
                "space, and the value per line), at line %d"
                % number)
        key, raw_value = parts
        if key in seen:
            return (
                "cause: a duplicate key (rule: each config "
                "key stands once), at line %d" % number)
        seen.add(key)
        if key in limit_keys and not raw_value.isdigit():
            return (
                "cause: a value of the wrong form for its "
                "key (rule: the value stands in the form "
                "its key states), at line %d" % number)
    return (
        "cause: the file does not stand valid under the "
        "config rules the brief states at CL19-164")


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

    A filesystem failure on the install route stands
    reported as a governed recorded error, never as a raw
    operating system error reaching the caller: the
    wrapping below carries every OSError the route raises
    into the InstallError form, whose code stands in the
    item 126 exit table."""
    try:
        return _install_impl(location=location, home=home)
    except OSError as exc:
        raise InstallError(
            "DESTINATION_EXISTS",
            "the install filesystem operation failed: %s"
            % (exc,))


def _install_impl(location=None, home=None):
    # The Python floor stands enforced before any file
    # is placed: Citeline requires Python 3.11 or later,
    # and an older interpreter meets a recorded install
    # error naming the floor (Step 19 register entry
    # R19-068).
    if tuple(sys.version_info[:2]) < (3, 11):
        raise InstallError(
            "PYTHON_FLOOR",
            "Citeline requires Python 3.11 or later; "
            "this interpreter is Python %d.%d, so no "
            "files stand placed"
            % tuple(sys.version_info[:2]))
    if location is None or home is None:
        raise InstallError(
            "MALFORMED_CALL",
            "install names a location and a home")
    if location == "" or home == "":
        # An empty string names no path at all: the shape
        # stands as a malformed call at exit 2, as the
        # same shape through the shell does, never as a
        # filesystem failure over the empty path.
        raise InstallError(
            "MALFORMED_CALL",
            "install names a location and a home, and an "
            "empty string names neither")
    location = os.path.abspath(str(location))
    home = os.path.abspath(str(home))
    _check_no_overlap(location)
    created_items = []
    location_stood = os.path.lexists(location)
    home_stood = os.path.lexists(home)
    if os.path.lexists(location):
        info = os.lstat(location)
        if not stat.S_ISDIR(info.st_mode):
            _fail(
                "the install location path stands as a file, "
                "not a directory: %s" % location)
    if os.path.lexists(home):
        # One created item, the product home, must stand
        # as a directory at the end of a completed
        # install: a home path standing as a file is
        # refused, as the location path standing as a
        # file is refused.
        info = os.lstat(home)
        if not stat.S_ISDIR(info.st_mode):
            _fail(
                "the product home path stands as a file, "
                "not a directory: %s" % home)
    config_file = os.path.join(location, CONFIG_FILE_NAME)
    config_warnings = []
    if os.path.lexists(config_file):
        # A config path that stands but is not a regular
        # file (a directory at the path) holds no config
        # file that parses, and fails the install at row
        # X-1 as an invalid config; a link to a regular
        # file stands checked through the link, as a
        # file.
        if not os.path.isfile(config_file):
            raise InstallError(
                "CONFIG_INVALID",
                "the config path stands but is not a "
                "regular file, so no config file that "
                "parses stands at the location: %s"
                % config_file)
        valid, config_warnings = _config_check(
            config_file, home)
        if not valid:
            raise InstallError(
                "CONFIG_INVALID",
                "an existing config file that is itself "
                "invalid fails the install, with the file "
                "still left untouched: %s (%s)"
                % (config_file,
                   _config_fault_detail(config_file)))
    if not os.path.lexists(location):
        os.makedirs(location)
        created_items.append(location)
    product_file = os.path.join(location, PRODUCT_FILE_NAME)
    product_text = _product_file_text()
    product_file_state = "created"
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
        if standing == product_text:
            product_file_state = "standing"
        elif _is_product_file(product_file):
            # The upgrade path: a standing launcher that is
            # this product file, from an earlier tree or an
            # earlier version, is replaced in place with the
            # launcher of the tree now installing, and the
            # package copy below is refreshed from the same
            # tree, so a newer tree installs over a standing
            # installation by running the installer again.
            with open(product_file, "w",
                      encoding="utf-8") as handle:
                handle.write(product_text)
            product_file_state = "upgraded"
        else:
            _fail(
                "a pre existing file that is not the product "
                "file stands at the product file path and "
                "stands never overwritten: %s" % product_file)
    else:
        _create_file_exclusive(product_file, product_text,
                               home=home)
        created_items.append(product_file)
    package_dir = os.path.join(location, PACKAGE_DIR_NAME)
    source_dir = os.path.join(_PRODUCT_DIR, PACKAGE_DIR_NAME)
    package_stood = os.path.lexists(package_dir)
    if package_stood:
        info = os.lstat(package_dir)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(
                info.st_mode):
            _fail(
                "a pre existing item that is not the product "
                "package stands at the package path: %s"
                % package_dir)
    else:
        os.makedirs(package_dir)
        created_items.append(package_dir)
    for name in sorted(os.listdir(source_dir)):
        if name == "__pycache__" or name.endswith(".pyc"):
            continue
        source_file = os.path.join(source_dir, name)
        if not os.path.isfile(source_file):
            continue
        shutil.copyfile(
            source_file, os.path.join(package_dir, name))
    if os.path.lexists(config_file):
        if os.path.isfile(config_file) and _is_installer_config(
                config_file):
            config_state = "installer config standing"
        else:
            config_state = "pre-existing config left untouched"
    else:
        _create_file_exclusive(
            config_file, _config_text(home), home=home)
        config_state = "config created by the installer"
        created_items.append(config_file)
    if not os.path.lexists(home):
        os.makedirs(home)
        created_items.append(home)
    _restrict(home, 0o700)
    _restrict(os.path.join(home, "journal.jsonl"), 0o600)
    _restrict(os.path.join(home, CONFIG_FILE_NAME), 0o600)
    if config_state != "pre-existing config left untouched":
        _restrict(config_file, 0o600)
    standing_items = []
    if location_stood:
        standing_items.append(location)
    if product_file_state in ("standing", "upgraded"):
        standing_items.append(product_file)
    if package_stood:
        standing_items.append(package_dir)
    if config_state in (
            "installer config standing",
            "pre-existing config left untouched"):
        standing_items.append(config_file)
    if home_stood:
        standing_items.append(home)
    return {
        "location": location,
        "home": home,
        "config": config_state,
        "product_file_state": product_file_state,
        "standing_items": standing_items,
        "warnings": config_warnings,
        "created_items": created_items,
        "complete": True,
    }


def uninstall(location=None, home=None, **_ignored):
    """Uninstall over the created items list only, resumably.

    Each created item stands removed under the lstat rule: a
    link loses itself only, a regular product file stands
    removed, an installer created config stands removed, and
    a config the installer did not create stands left. The
    home stands removed with everything in it, journal
    contents included, and the location directory stands
    removed where it stands empty after those removals. A
    repeat call over a part removed state completes the list
    and reports completion. A filesystem failure on the route
    stands reported as a governed recorded error, as on the
    install route."""
    try:
        return _uninstall_impl(location=location, home=home)
    except OSError as exc:
        raise InstallError(
            "DESTINATION_EXISTS",
            "the uninstall filesystem operation failed: %s"
            % (exc,))


_LAUNCHER_MARKER = "Citeline launcher for one local installation"


def _is_product_file(path):
    """True where the file at the product file path is this
    product file: the exact launcher text for this location,
    or a launcher carrying the Citeline launcher marker, as
    a launcher installed from another tree path does. A file
    of any other content is a foreign file the installer
    never created, however it is named."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    if _LAUNCHER_MARKER in text and "_PACKAGE_PARENT" in text:
        return True
    return False


def _config_home_value(path):
    """The home value a config file at the install location
    names, or None where it names none."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("home") and "=" in line:
                    return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def _home_is_product_home(home):
    """True where the home holds the files the product
    itself creates there: the journal or its write lock."""
    for name in ("journal.jsonl", ".citeline-write.lock"):
        if os.path.lexists(os.path.join(home, name)):
            return True
    return False


def _home_linked(location, home):
    """True where the installation at the location names
    this home: the config file at the location, installer
    created or standing, carries a home line for it."""
    named = _config_home_value(
        os.path.join(location, CONFIG_FILE_NAME))
    if named is None:
        return False
    return os.path.abspath(named) == os.path.abspath(home)


def _remove_home_tree(home, removed):
    """Remove a product home and everything in it.

    The walk never follows a link: a link inside the home
    loses the link itself only, and the file the link names
    stands untouched, as at every other created item path.
    """
    for dirpath, dirnames, filenames in os.walk(
            home, topdown=False):
        for name in filenames:
            path = os.path.join(dirpath, name)
            os.unlink(path)
            removed.append(path)
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                os.unlink(path)
                removed.append(path)
            else:
                try:
                    os.rmdir(path)
                    removed.append(path)
                except OSError:
                    pass
    os.rmdir(home)
    removed.append(home)


def _uninstall_impl(location=None, home=None):
    if location is None or home is None:
        raise InstallError(
            "MALFORMED_CALL",
            "uninstall names a location and a home")
    if location == "" or home == "":
        raise InstallError(
            "MALFORMED_CALL",
            "uninstall names a location and a home, and an "
            "empty string names neither")
    location = os.path.abspath(str(location))
    home = os.path.abspath(str(home))
    removed = []
    remaining = []
    evidence = False
    product_file = os.path.join(location, PRODUCT_FILE_NAME)
    config_file = os.path.join(location, CONFIG_FILE_NAME)
    for path in (product_file, config_file):
        if not os.path.lexists(path):
            continue
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(path)
            removed.append(path)
            evidence = True
        elif stat.S_ISREG(info.st_mode):
            if path == config_file and not _is_installer_config(
                    path):
                remaining.append(path)
                continue
            if path == product_file and not _is_product_file(
                    path):
                remaining.append(path)
                continue
            os.unlink(path)
            removed.append(path)
            evidence = True
        else:
            remaining.append(path)
    package_dir = os.path.join(location, PACKAGE_DIR_NAME)
    if os.path.lexists(package_dir):
        info = os.lstat(package_dir)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(package_dir)
            removed.append(package_dir)
            evidence = True
        elif stat.S_ISDIR(info.st_mode) and os.path.isfile(
                os.path.join(package_dir, "__init__.py")):
            _remove_home_tree(package_dir, removed)
            evidence = True
        else:
            remaining.append(package_dir)
    if os.path.lexists(home):
        info = os.lstat(home)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(home)
            removed.append(home)
        elif stat.S_ISDIR(info.st_mode):
            linked = _home_linked(location, home) or \
                _home_is_product_home(home) or (
                    evidence and not os.listdir(home))
            if linked:
                _remove_home_tree(home, removed)
            else:
                remaining.append(home)
        else:
            remaining.append(home)
    if os.path.lexists(location):
        info = os.lstat(location)
        if stat.S_ISLNK(info.st_mode):
            os.unlink(location)
            removed.append(location)
        elif stat.S_ISDIR(info.st_mode):
            if evidence:
                try:
                    os.rmdir(location)
                    removed.append(location)
                except OSError:
                    remaining.append(location)
            else:
                remaining.append(location)
        else:
            remaining.append(location)
    return {
        "location": location,
        "home": home,
        "removed": removed,
        "remaining": remaining,
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


_USAGE_LINES = (
    "usage: python install.py [install location]",
    "usage: python install.py uninstall "
    "[install location] [home]",
    "usage: python install.py --location [location] "
    "--home [home]",
)


def _print_usage(stream):
    for line in _USAGE_LINES:
        print(line, file=stream)
    print(
        "run python install.py --help for the full help "
        "text", file=stream)


def _print_help():
    print("citeline installer")
    _print_usage(sys.stdout)
    print(
        "install creates the product file, the package "
        "copy, and the installer config in the install "
        "location, and the product home where none stands")
    print(
        "uninstall removes only what the installer "
        "created, the used home and its journal contents "
        "included, and names everything that remains")
    print(
        "running the installer of a newer tree over a "
        "standing installation upgrades it in place")
    print(
        "the flag forms --location and --home stand "
        "accepted beside the positional forms, and "
        "--uninstall stands beside the word uninstall")


def _malformed(message):
    """A malformed installer call, answered in full: what
    happened, the usage, the next step, and the statement
    that nothing was installed or removed, because a call
    that fails to parse runs no route at all."""
    print("install: MALFORMED_CALL: %s" % message,
          file=sys.stderr)
    _print_usage(sys.stderr)
    print(
        "next step: correct the call as the usage states "
        "and run it again", file=sys.stderr)
    print("nothing was installed or removed", file=sys.stderr)
    return 2


def _print_error_furniture(mode):
    _print_usage(sys.stderr)
    print(
        "next step: correct the fault named above and run "
        "the call again; a repeat call completes what "
        "stands part done", file=sys.stderr)
    if mode == "uninstall":
        print(
            "the uninstall did not complete by this call",
            file=sys.stderr)
    else:
        print(
            "the install did not complete by this call",
            file=sys.stderr)


def main(argv=None):
    """The install.py invocation, with its uninstall mode.

    The stated form: install.py run with the system Python
    from the shipped product directory, with one optional
    argument naming the install location; uninstall is the
    word uninstall as the first argument, with the install
    location as its optional second argument and the same
    default, and the home as an optional third argument
    where the install was made with a non default home.
    The flag spellings --location and --home, and
    the --uninstall flag, stand accepted beside the stated
    form. The output stands in the simple form only and
    states the home path.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--help", "-h", "help"):
        _print_help()
        return 0
    mode = "install"
    location = None
    home = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "uninstall" and mode == "uninstall" \
                and index != 0:
            # The mode word stands consumed once: a second
            # uninstall word is no location, and the call
            # stands malformed instead of silently
            # uninstalling a directory named uninstall.
            return _malformed(
                "the uninstall mode stands named twice")
        if token == "uninstall" and index == 0:
            mode = "uninstall"
            index += 1
        elif token == "--uninstall":
            mode = "uninstall"
            index += 1
        elif token in ("--location", "--home"):
            if index + 1 >= len(argv):
                return _malformed("%s names a value" % token)
            if token == "--location":
                location = argv[index + 1]
            else:
                home = argv[index + 1]
            index += 2
        elif not token.startswith("-") and location is None:
            location = token
            index += 1
        elif not token.startswith("-") and mode == "uninstall" \
                and home is None:
            # The documented uninstall form names the home as
            # its second positional argument, beside the flag
            # form, so an uninstall made with a non default
            # home acts on the home named and never silently
            # against the default home.
            home = token
            index += 1
        else:
            return _malformed(
                "unrecognised argument: %s" % token)
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
            for remaining in report.get("remaining") or []:
                print("remaining: %s" % remaining)
            if not report.get("removed"):
                print("nothing was removed")
                if not report.get("remaining"):
                    print(
                        "nothing was found: no installation "
                        "stood at the location or the home "
                        "named")
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
            for standing in report.get("standing_items") or []:
                print("standing: %s" % standing)
            standing_items = report.get("standing_items") or []
            if os.path.join(
                    report["location"], PRODUCT_FILE_NAME) \
                    in standing_items and report["home"] \
                    in standing_items:
                print(
                    "the product file and the home already "
                    "stand complete")
    except InstallError as exc:
        print("install: %s" % (exc,), file=sys.stderr)
        _print_error_furniture(mode)
        return exc.exit_code
    except OSError as exc:
        # The entry point backstop of the same discipline:
        # no filesystem failure of either route reaches
        # the operator as a traceback at a code the table
        # assigns to no outcome.
        wrapped = InstallError(
            "DESTINATION_EXISTS",
            "the install filesystem operation failed: %s"
            % (exc,))
        print("install: %s" % (wrapped,), file=sys.stderr)
        _print_error_furniture(mode)
        return wrapped.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
