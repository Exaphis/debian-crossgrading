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
        # set LC_ALL=C so we can rely on command output being English
        os.environ['LC_ALL'] = 'C'

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
    def _fix_dpkg_errors(packages):
        """Tries to fix the given packages that dpkg failed to install.

        First, run apt install -f.

        If the errors are still not fixed, remove all other co-installed packages
        for packages declared M-A: same.

        Returns:
            True if all errors were fixed, False otherwise.
        """

        print('Running apt-get --fix-broken install...')
        # let user select yes/no
        process = subprocess.run(['apt-get', 'install', '-f'], check=False)
        if process.returncode == 0:
            return True

        print('apt-get --fix-broken install failed.')
        print('Removing all coinstalled packages...')
        for package in packages:
            package_status = subprocess.run(['dpkg', '-s', package],
                                            stdout=subprocess.PIPE, stderr=sys.stderr,
                                            encoding='UTF-8', check=True).stdout.splitlines()
            if 'Multi-Arch: same' not in package_status:
                continue

            # architecture should be specified for M-A: same packages
            assert ':' in package

            short_name = package[:package.index(':')]
            coinstalled = subprocess.check_output(['dpkg-query', '-f',
                                                   '${Package}:${Architecture}\n', '-W',
                                                   short_name],
                                                  encoding='UTF-8').splitlines()
            for coinstalled_package in coinstalled:
                if coinstalled_package == package:
                    continue

                process = subprocess.run(['dpkg', '--remove', '--force-depends',
                                          coinstalled_package], check=False)
                if process.returncode != 0:
                    print(f'dpkg failed to remove {coinstalled_package}.')

                    prerm_script = f'/var/lib/dpkg/info/{coinstalled_package}.prerm'
                    if os.path.isfile(prerm_script):
                        cont = input('Remove prerm script and try again [Y/n]? ').lower()

                        if cont == 'y' or not cont:
                            os.remove(prerm_script)

                            subprocess.run(['dpkg', '--remove', '--force-depends',
                                            coinstalled_package], check=False)

        print('Running dpkg --configure -a ...')
        process = subprocess.run(['dpkg', '--configure', '-a'], check=False)
        if process.returncode != 0:
            return False

        print('Running apt-get --fix-broken install...')
        process = subprocess.run(['apt-get', 'install', '-f'], check=False)
        if process.returncode == 0:
            return True

        return False

    @staticmethod
    def _install_and_configure(debs_to_install):
        """Runs one pass of dpkg -i and dpkg --configure -a on the input .deb files.

        dpkg outputs failures in two ways: the .deb file that failed,
        or the package name that failed.

        .deb files are outputted if the installation totally failed in some way
        (dependency error, etc.), so that the package wasn't added to the database.
        They should be retried later.

        package names are outputted if the installation didn't completely fail.
        The errors should be fixed, and then dpkg --configure -a should be run.

        Returns:
            A list of .debs that failed to be installed, and a list of packages
            that failed to be installed.
        """

        # set max error count so dpkg does not abort from too many errors
        # multiply by 2 because a package can have multiple errors
        max_error_count = max(50, len(debs_to_install) * 2)

        # display stdout, parse stderr for packages to try and reinstall
        errs = subprocess.run(['dpkg', '-i', f'--abort-after={max_error_count}',
                               *debs_to_install], encoding='UTF-8',
                              stdout=sys.stdout, stderr=subprocess.PIPE,
                              check=False).stderr.splitlines()

        failed_debs = []
        failed_packages = []

        capture_packages = False

        if errs:
            print('Errors:')

            for line in errs:
                print(line)
                line = line.strip()

                if capture_packages:
                    if line.endswith('.deb'):
                        assert os.path.isfile(line), f'{line} does not exist'
                        failed_debs.append(line)
                    else:
                        failed_packages.append(line)

                if line == 'Errors were encountered while processing:':
                    capture_packages = True

        print('Running dpkg --configure -a...')
        subprocess.run(['dpkg', '--configure', '-a',
                        f'--abort-after={max_error_count}'], check=False,
                       stdout=sys.stdout, stderr=sys.stderr)

        return failed_debs, failed_packages

    @staticmethod
    def install_packages(debs_to_install=None):
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
        if debs_to_install is None:
            debs_to_install = glob('/var/cache/apt/archives/*.deb')

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
        debs_remaining = debs_to_install
        failed_packages = None

        while debs_remaining:
            loop_count += 1
            print(f'dpkg -i/--configure loop #{loop_count}')

            failed_debs, failed_packages = Crossgrader._install_and_configure(debs_remaining)

            for deb in debs_remaining:
                if deb not in failed_debs:
                    os.remove(deb)

            assert len(failed_debs) <= len(debs_remaining)

            if len(failed_debs) == len(debs_remaining):
                print('Number of failed installs did not decrease, halting...')
                debs_remaining = failed_debs
                break

            debs_remaining = failed_debs

            if debs_remaining:
                print('The following .deb files were not fully installed, retrying...')
                for deb in debs_remaining:
                    print(f'\t{deb}')

        if debs_remaining:
            raise PackageInstallationError(debs_remaining)

        if failed_packages:
            fixed = Crossgrader._fix_dpkg_errors(failed_packages)
            if not fixed:
                print('Some dpkg errors could not be fixed automatically.')

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
        for name_with_arch in package_names:
            if ':' in name_with_arch:
                name, arch = name_with_arch.split(':')
            else:
                name = name_with_arch
                arch = self.target_arch

            # dpkg will not find the package if the specified architecture
            # is the same as the current architecture
            # it expects <name> instead of <name:arch>
            if arch == self.current_arch:
                target_name = name
            else:
                target_name = f'{name}:{arch}'

            try:
                package = self._apt_cache[target_name]

                if not ignore_installed or not package.is_installed:
                    packages.append(package)
            except KeyError:
                if not ignore_unavailable_targets:
                    raise PackageNotFoundError(name_with_arch)
                print(f'Couldn\'t find {name_with_arch}, ignoring...')
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

    @staticmethod
    def get_arch_packages(foreign_arch):
        """Returns all the packages in the given architecture."""
        installed_packages = subprocess.check_output(['dpkg-query', '-f',
                                                      '${Package}:${Architecture}\n',
                                                      '-W'], encoding='UTF-8').splitlines()

        return [pkg for pkg in installed_packages if pkg.split(':')[1] == foreign_arch]


def first_stage(args):
    """Runs first stage of the crossgrade process.

    Installs initramfs packages and packages with Priority: required/important.
    Does not need to be run if the target architecture can run the existing architecture.
    """
    with Crossgrader(args.target_arch) as crossgrader:
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


def second_stage(args):
    """Runs the second stage of the crossgrade process.

    Crossgrades all packages that are not in the target architecture.
    """
    with Crossgrader(args.target_arch) as crossgrader:
        targets = crossgrader.list_second_stage_targets(
            ignore_unavailable_targets=args.force_unavailable
        )

        print(f'{len(targets)} targets found.')
        cont = input('Do you want to continue [y/N]? ').lower()
        if cont == 'y':
            crossgrader.cache_package_debs(targets)

            if not args.download_only:
                crossgrader.install_packages()
        else:
            print('Aborted')


def third_stage(args):
    """Runs the third stage of the crossgrading process.

    Removes all packages from the given architecture.
    """
    with Crossgrader(args.target_arch) as crossgrader:
        # TODO: implement package exclusion
        foreign_arch = args.third_stage
        targets = crossgrader.get_arch_packages(foreign_arch)

        print(f'{len(targets)} targets found.')
        for pkg_name in sorted(targets):
            print(pkg_name)

        cont = input('Do you want to continue [y/N]? ').lower()
        if cont == 'y':
            subprocess.check_call(['dpkg', '--purge', *targets])
            remaining = crossgrader.get_arch_packages(foreign_arch)
            if remaining:
                print('The following packages could not be successfully purged:')
                for pkg_name in remaining:
                    print(f'\t{pkg_name}')
            else:
                print('All target successfully purged.')
                print((f'If desired, run dpkg --remove-architecture {foreign_arch} to '
                       'complete the crossgrade.'))


def install_from(args):
    """Installs all .debs from the specified location."""
    with Crossgrader(args.target_arch) as crossgrader:
        debs = glob(f'{args.install_from}/*.deb')
        print('Installing the following .debs:')
        for deb in debs:
            print(f'\t{deb}')

        cont = input('Do you want to continue [y/N]? ').lower()
        if cont == 'y':
            crossgrader.install_packages(debs)
        else:
            print('Aborted.')


def main():
    """Crossgrade driver, executed only if run as script"""
    parser = argparse.ArgumentParser()
    parser.add_argument('target_arch', help='Target architecture of the crossgrade')
    parser.add_argument('--second-stage',
                        help=('Run the second stage of the crossgrading process '
                              '(crossgrading all remaining packages)'),
                        action='store_true')
    parser.add_argument('--third-stage',
                        help=('Run the third stage of the crossgrading process '
                              '(removing all packages under specified arch)'),
                        nargs='?')
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

    if args.install_from:
        install_from(args)
    elif args.second_stage:
        second_stage(args)
    elif args.third_stage:
        third_stage(args)
    else:
        first_stage(args)


if __name__ == '__main__':
    main()
