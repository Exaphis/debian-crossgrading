"""Debian crossgrading tool

Exceptions:
    CrossgradingError: Base class for crossgrading exceptions
    InvalidArchitectureError: Input architecture was invalid
    PackageInstallationError: Package failed to be installed
    RemnantInitramfsHooksError: An initramfs hook could not be linked to an installed package
    PackageNotFoundError: Package couldn't be found in the target architecture

Classes:
    Crossgrader: contains tools to perform system crossgrade
"""


import argparse
from glob import glob
import os
import subprocess
import sys
import traceback

import apt


class CrossgradingError(Exception):
    """Base class for crossgrading exceptions."""


class InvalidArchitectureError(CrossgradingError):
    """Raised when a given architecture is not recognized by dpkg."""


class PackageInstallationError(CrossgradingError):
    """Raised when an error occurs while packages are being installed.

    Attributes:
        packages: A list of .deb files that were not installed.
    """

    def __init__(self, packages):
        super().__init__('An error occurred installing the '
                         f'following packages: {str(packages)}')
        self.packages = packages


class RemnantInitramfsHooksError(CrossgradingError):
    """Raised when not all initramfs hooks could be accounted for.

    Attributes:
        remnant_hooks: A list of paths to hooks that could not be linked
            to a package that will be crossgraded.
    """

    def __init__(self, hooks):
        super().__init__('The following initramfs hooks could not be '
                         f'linked to packages: {str(hooks)}')
        self.hooks = hooks


class PackageNotFoundError(CrossgradingError):
    """Raised when a package does not exist in APT's cache.

    Attributes:
        package: The name of the package that could not be found.
    """

    def __init__(self, package):
        super().__init__(f'{package} could not be found in APT\'s cache')
        self.package = package


class Crossgrader:
    """Finds packages to crossgrade and crossgrades them.

    Attributes:
        target_arch: A string representing the target architecture of dpkg.
        current_arch: A string representing the current architecture of dpkg.
    """

    def __init__(self, target_architecture):
        """Inits Crossgrader with the given target architecture.

        Raises:
            InvalidArchitectureError: The given target_architecture is not recognized
                by dpkg.
        """
        valid_architectures = subprocess.check_output(['dpkg-architecture', '--list-known'],
                                                      encoding='UTF-8').splitlines()
        if target_architecture not in valid_architectures:
            raise InvalidArchitectureError(f'{target_architecture} is not recognized by dpkg.')

        subprocess.check_call(['dpkg', '--add-architecture', target_architecture])

        self.current_arch = subprocess.check_output(['dpkg', '--print-architecture'],
                                                    encoding='UTF-8')

        self.target_arch = target_architecture

        self._apt_cache = apt.Cache()

        try:
            self._apt_cache.update(apt.progress.text.AcquireProgress())
            self._apt_cache.open()  # re-open to utilise new cache
        except apt.cache.FetchFailedException:
            traceback.print_exc()
            print('Ignoring...')

    def __enter__(self):
        """Enter the with statement"""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Exit the with statement"""
        self.close()

    def close(self):
        """Close the package cache"""
        self._apt_cache.close()

    @staticmethod
    def install_packages(packages_to_install=None):
        """Installs specified .deb files.

        Installs the .deb files specified in packages_to_install
        using a looping dpkg -i *.deb / dpkg --configure -a.

        Args:
            packages_to_install: A list of paths to .deb files. If it is None,
                all .debs in APT's cache will be installed.

        Raises:
            PackageInstallationError: Some of the packages were not successfully
                installed/configured.
        """
        if packages_to_install is None:
            packages_to_install = glob('/var/cache/apt/archives/*.deb')

        # unfeasible to perform a topological sort (complex/circular dependencies, etc.)
        # easier to install/reconfigure repeatedly until errors resolve themselves

        # use dpkg to perform the crossgrade because apt does not realize that crossgrading
        # a package will not necessarily break it because of qemu user emulation
        # e.g. apt refuses to install perl-base

        # crossgrade in one call to prevent repeat triggers
        # (e.g. initramfs rebuild), saving time

        # TODO: Experiment with Guillem's suggestion
        # https://blog.zugschlus.de/archives/972-How-to-amd64-an-i386-Debian-installation-with-multiarch.html#c24572
        # Summary: Use dpkg --unpack; dpkg --configure --pending instead of dpkg -i?
        loop_count = 0
        packages_remaining = packages_to_install
        while packages_remaining:
            loop_count += 1

            print(f'dpkg -i/--configure loop #{loop_count}')
            # display stdout, parse stderr for packages to try and reinstall
            errs = subprocess.run(['dpkg', '-i', *packages_remaining], encoding='UTF-8',
                                  stdout=sys.stdout,
                                  stderr=subprocess.PIPE, check=False).stderr.splitlines()

            failures = []
            capture_packages = False
            print('Errors:')
            for line in errs:
                print(line)
                line = line.strip()
                if capture_packages and line.endswith('.deb'):
                    failures.append(line)
                    assert os.path.isfile(line), f'{line} does not exist'

                if line == 'Errors were encountered while processing:':
                    capture_packages = True

            print('Running dpkg --configure -a...')
            subprocess.run(['dpkg', '--configure', '-a'], check=False,
                           stdout=sys.stdout, stderr=sys.stderr)

            for deb in packages_remaining:
                if deb not in failures:
                    os.remove(deb)

            if len(failures) >= len(packages_remaining):
                print('Number of failed installs did not decrease, halting...')
                packages_remaining = failures
                break

            packages_remaining = failures

            if packages_remaining:
                print('The following packages were not fully installed, retrying...')
                for package in packages_remaining:
                    print(f'\t{package}')

        if packages_remaining:
            raise PackageInstallationError(packages_remaining)

    def cache_package_debs(self, targets):
        """Cache specified packages.

        Clears APT's .deb cache, then downloads specified packages
        to /var/apt/cache/archives using python-apt.

        Args:
            targets: A list of apt.package.Package objects to crossgrade.
        """

        # clean /var/cache/apt/archives for download
        # is there a python-apt function for this?
        subprocess.check_call(['apt-get', 'clean'])

        # use python-apt to cache .debs for package and dependencies
        # because apt-get --download-only install will not download
        # if it can't find a good way to resolve dependencies

        for target in targets:
            target.mark_install(auto_fix=False)  # do not try to fix broken packages

        # fetch_archives() throws a more detailed error if a specific package
        # could not be downloaded for some reason.
        # Do not check its return value; it is undefined.
        self._apt_cache.fetch_archives()

        self._apt_cache.clear()

    def _is_first_stage_target(self, package):
        """Returns a boolean of whether or not the apt.package.Package is a first stage target.

        A first stage target is a package with Priority: required/important.

        This function does not check if the package has installed initramfs hooks.

        Without first stage targets being crossgraded, the system will fail to reboot to the
        new architecture or will be useless after reboot.
        """
        if not package.is_installed:
            return False

        # do not use package.architecture() because Architecture: all packages
        # returns the native architecture
        if package.installed.architecture in ('all', self.target_arch):
            return False

        if package.installed.priority in ('required', 'important'):
            return True

        return False

    def find_packages_from_names(self, package_names,
                                 ignore_unavailable_targets=False,
                                 ignore_installed=True):
        """Returns a list of apt.package.Package objects corresponding to the given names.

        If no architecture is specified, it defaults to the target architecture.

        Args:
            package_names: A list of package names
            ignore_unavailable_targets: If true, ignore names that have no corresponding
                packages
            ignore_installed: If true, ignore packages that have already been installed

        Raises:
            PackageNotFoundError: A package requested was not available in APT's cache.
        """
        packages = []
        for name in package_names:
            name_with_arch = name if ':' in name else f'{name}:{self.target_arch}'

            try:
                package = self._apt_cache[name_with_arch]

                if not ignore_installed or not package.is_installed:
                    packages.append(package)
            except KeyError:
                if not ignore_unavailable_targets:
                    raise PackageNotFoundError(name_with_arch)

        return packages

    def list_first_stage_targets(self, ignore_initramfs_remnants=False,
                                 ignore_unavailable_targets=False):
        """Returns a list of apt.package.Package objects that must be crossgraded before reboot.

        Retrieves and returns a list of all packages with Priority: required/important
        or installed initramfs hooks.

        Args:
            ignore_initramfs_remnants: If true, do not raise a RemnantInitramfsHooksError if
                there are initramfs hooks that could not be linked.
            ignore_unavailable_targets: If true, do not raise a PackageNotFoundError if a package
                could not be found in the target architecture.

        Raises:
            RemnantInitramfsHooksError: Some initramfs hooks could not be linked to a
                first stage target package.
            PackageNotFoundError: A required package in the target architecture was not available
                in APT's cache.
        """

        unaccounted_hooks = set(glob('/usr/share/initramfs-tools/hooks/*'))
        targets = set()

        hook_packages = subprocess.check_output(['dpkg-query', '-S',
                                                 '/usr/share/initramfs-tools/hooks/*'],
                                                encoding='UTF-8').splitlines()
        for hook_package in hook_packages:
            name, hook = hook_package.split(': ')

            if hook not in unaccounted_hooks:
                print(f'Expected {name} to contain an initramfs hook, but it does not.')
                print(f'Skipping {name}.')
                continue

            unaccounted_hooks.remove(hook)

            package = self._apt_cache[name]

            if not package.is_installed:
                print((f'WARNING: {package}, containing an initramfs hook, ',
                       'is marked as not fully installed.'))
                print('Assuming it is installed.')
                architecture = package.candidate.architecture
            else:
                architecture = package.installed.architecture

            if architecture not in ('all', self.target_arch):
                targets.add(package.shortname)

        if unaccounted_hooks and not ignore_initramfs_remnants:
            raise RemnantInitramfsHooksError(unaccounted_hooks)

        # looping through the APT cache using python-apt takes 10+ seconds on
        # some systems
        # dpkg-query instead takes <1 second
        installed_packages = subprocess.check_output(['dpkg-query', '-f',
                                                      '${Package}:${Architecture}\n',
                                                      '-W'], encoding='UTF-8').splitlines()

        for full_name in installed_packages:
            package = self._apt_cache[full_name]
            if self._is_first_stage_target(package):
                targets.add(package.shortname)

        targets = [f'{short_name}:{self.target_arch}' for short_name in targets]
        return self.find_packages_from_names(targets, ignore_unavailable_targets)

    def list_second_stage_targets(self, ignore_unavailable_targets):
        """Returns a list of apt.package.Package objects that are not in the target architecture.

        Args:
            ignore_unavailable_targets: If true, do not raise a PackageNotFoundError if a package
                could not be found in the target architecture.

        Raises:
            PackageNotFoundError: A required package in the target architecture was not available
                in APT's cache.
        """

        targets = set()
        installed_packages = subprocess.check_output(['dpkg-query', '-f',
                                                      '${Package}:${Architecture}\n',
                                                      '-W'], encoding='UTF-8').splitlines()
        for full_name in installed_packages:
            package = self._apt_cache[full_name]

            if not package.is_installed:
                continue

            if package.installed.architecture not in ('all', self.target_arch):
                targets.add(package.shortname)

        targets = [f'{short_name}:{self.target_arch}' for short_name in targets]
        return self.find_packages_from_names(targets, ignore_unavailable_targets)


def main():
    """Crossgrade driver, executed only if run as script"""
    parser = argparse.ArgumentParser()
    parser.add_argument('target_arch', help='Target architecture of the crossgrade')
    parser.add_argument('--second-stage',
                        help='Run the second stage of the crossgrading process',
                        action='store_true')
    parser.add_argument('--download-only',
                        help='Perform target package listing and download, but not installation',
                        action='store_true')
    parser.add_argument('--install-from',
                        help=('Perform .deb installation from a specified location '
                              '(default: /var/cache/apt/archives), '
                              'but not package listing and download'),
                        nargs='?', const='/var/cache/apt/archives')
    parser.add_argument('--force-unavailable',
                        help=('Force crossgrade even if not all packages to be crossgraded'
                              ' are available in the target architecture'),
                        action='store_true')
    parser.add_argument('--force-initramfs',
                        help=('Force crossgrade even if not all initramfs'
                              ' hooks could be crossgraded'),
                        action='store_true')
    parser.add_argument('-f', '--force-all',
                        help='Equivalent to --force-install --force-initramfs',
                        action='store_true')
    parser.add_argument('-p', '--packages',
                        help=('Crossgrade the subsequent package names and nothing else'),
                        nargs='+')
    args = parser.parse_args()

    if args.force_all:
        args.force_initramfs = True
        args.force_unavailable = True

    with Crossgrader(args.target_arch) as crossgrader:
        if args.install_from:
            debs = glob(f'{args.install_from}/*.deb')
            print('Installing the following .debs:')
            for deb in debs:
                print(f'\t{deb}')

            cont = input('Do you want to continue [y/N]? ').lower()
            if cont == 'y':
                crossgrader.install_packages(debs)
            else:
                print('Aborted.')
        elif args.second_stage:
            targets = crossgrader.list_second_stage_targets(
                ignore_unavailable_targets=args.force_unavailable
            )

            print(f'{len(targets)} targets found.')
            for pkg_name in sorted(map(lambda pkg: pkg.fullname, targets)):
                print(pkg_name)

            cont = input('Do you want to continue [y/N]? ').lower()
            if cont == 'y':
                crossgrader.cache_package_debs(targets)

                if not args.download_only:
                    crossgrader.install_packages()
            else:
                print('Aborted')
        else:
            if args.packages:
                targets = crossgrader.find_packages_from_names(args.packages)
            else:
                targets = crossgrader.list_first_stage_targets(
                    ignore_initramfs_remnants=args.force_initramfs,
                    ignore_unavailable_targets=args.force_unavailable
                )

            print(f'{len(targets)} targets found.')
            for pkg_name in sorted(map(lambda pkg: pkg.fullname, targets)):
                print(pkg_name)

            cont = input('Do you want to continue [y/N]? ').lower()
            if cont == 'y':
                crossgrader.cache_package_debs(targets)

                if not args.download_only:
                    crossgrader.install_packages()
            else:
                print('Aborted.')


if __name__ == '__main__':
    main()
