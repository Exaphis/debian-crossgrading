"""Functions for querying packages from dpkg"""

import subprocess

class PackageNotFoundError(Exception):
    """Raised when a package does not exist in APT's cache.

    Attributes:
        package: The name of the package that could not be found
    """

    def __init__(self, package):
        super().__init__("{} could not be found in APT's cache".format(package))
        self.package = package


def get_package_fullnames():
    """Returns the full names (name:arch) of all packages on the current system."""
    return subprocess.check_output(['dpkg-query', '-f', '${Package}:${Architecture}\n', '-W'],
                                   universal_newlines=True).splitlines()

def get_arch_packages(arch):
    """Returns the full names of all the packages with the given architecture."""
    return [pkg for pkg in get_package_fullnames() if pkg.split(':')[1] == arch]

def iter_package_objs(apt_cache):
    """Generator of all packages existing on the current system.

    Args:
        apt_cache: APT cache to get package objects
    """

    # looping through the APT cache using python-apt takes 10+ seconds on
    # some systems, whereas dpkg-query instead takes <1 second
    for fullname in get_package_fullnames():
        yield apt_cache[fullname]

def iter_packages_containing_files(apt_cache, *filename_patterns):
    """Generator of a tuple of (package_object, filename) outputted
    by dpkg-query -S filename_patterns."""
    # possible erroring out, use popen
    proc = subprocess.Popen(['dpkg-query', '-S'] + list(filename_patterns),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            universal_newlines=True)
    query_out_lines, __ = proc.communicate()
    query_out_lines = query_out_lines.splitlines()

    for query_out_line in query_out_lines:
        # yikes... how can I do this without depending on dpkg-query output format?
        names, filename = query_out_line.split(': ')

        for name in names.split(', '):
            # handle output that might not be packages (e.g. diversions)
            try:
                package = apt_cache[name]
            except KeyError:
                continue

            yield (package, filename)

def find_package_objs(names, apt_cache, default_arch=None, ignore_unavailable_targets=False,
                      ignore_installed=False):
    """Returns a list of apt.package.Package objects corresponding to the given names.

    Args:
        names: A list of package names
        apt_cache: APT cache to get package objects
        default_arch: Default architecture for names without specified architecture
        ignore_unavailable_targets: If true, ignore names that have no corresponding
            packages
        ignore_installed: If true, ignore packages that are already installed.

    Raises:
        PackageNotFoundError: A package requested was not available in APT's cache.
    """
    packages = []
    for name in names:
        if ':' in name:
            pkg_name, arch = name.split(':')
        else:
            pkg_name = name
            arch = default_arch

        target_name = '{}:{}'.format(pkg_name, arch) if arch is not None else name

        try:
            package = apt_cache[target_name]
            if not ignore_installed or not package.is_installed:
                packages.append(package)
        except KeyError:
            if not ignore_unavailable_targets:
                raise PackageNotFoundError(target_name)

            print("Couldn't find {}, ignoring...".format(target_name))

    return packages
