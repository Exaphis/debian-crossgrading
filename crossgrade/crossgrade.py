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
import shutil
import subprocess
import sys
import traceback

import apt

import cmd_utils


class CrossgradingError(Exception):
    """Base class for crossgrading exceptions."""


class InvalidArchitectureError(CrossgradingError):
    """Raised when a given architecture is not recognized by dpkg."""


class NotEnoughSpaceError(CrossgradingError):
    """Raised when there is not enough space left to download and install necessary packages."""


class PackageInstallationError(CrossgradingError):
    """Raised when an error occurs while packages are being installed.

    Attributes:
        packages: A list of .deb files that were not installed.
    """

    def __init__(self, packages):
        super().__init__('An error occurred installing the '
                         'following packages: {}'.format(packages))
        self.packages = packages


class RemnantInitramfsHooksError(CrossgradingError):
    """Raised when not all initramfs hooks could be accounted for.

    Attributes:
        remnant_hooks: A list of paths to hooks that could not be linked
            to a package that will be crossgraded.
    """

    def __init__(self, hooks):
        super().__init__('The following initramfs hooks could not be '
                         'linked to packages: {}'.format(hooks))
        self.hooks = hooks


class PackageNotFoundError(CrossgradingError):
    """Raised when a package does not exist in APT's cache.

    Attributes:
        package: The name of the package that could not be found.
    """

    def __init__(self, package):
        super().__init__('{} could not be found in APT\'s cache'.format(package))
        self.package = package


class Crossgrader:
    """Finds packages to crossgrade and crossgrades them.

    Attributes:
        target_arch: A string representing the target architecture of dpkg.
        current_arch: A string representing the current architecture of dpkg.
    """

    APT_CACHE_DIR = '/var/cache/apt/archives'
    DPKG_INFO_DIR = '/var/lib/dpkg/info'

    def __init__(self, target_architecture):
        """Inits Crossgrader with the given target architecture.

        Raises:
            InvalidArchitectureError: The given target_architecture is not recognized
                by dpkg.
        """
        # set LC_ALL=C so we can rely on command output being English
        os.environ['LC_ALL'] = 'C'

        valid_architectures = subprocess.check_output(['dpkg-architecture', '--list-known'],
                                                      universal_newlines=True).splitlines()
        if target_architecture not in valid_architectures:
            raise InvalidArchitectureError(
                'Architecture {} is not recognized by dpkg.'.format(target_architecture)
            )

        subprocess.check_call(['dpkg', '--add-architecture', target_architecture])

        self.current_arch = subprocess.check_output(['dpkg', '--print-architecture'],
                                                    universal_newlines=True).strip()
        self.target_arch = target_architecture

        script_dir = os.path.dirname(os.path.realpath(__file__))
        self.arch_check_hook_path = os.path.join(os.path.dirname(script_dir),
                                                 'arch-check-hook.sh')
        self.initramfs_functions_path = '/usr/share/initramfs-tools/hook-functions'
        self.initramfs_functions_backup_path = os.path.join(script_dir, 'hook-functions.bak')

        print('Installing initramfs binary architecture check hook...')
        if self.create_initramfs_arch_check():
            print('Hook installed.')
        else:
            print('Hook installation failed.')

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

    def create_initramfs_arch_check(self):
        """Inserts the contents of arch-check-hook.sh into the copy_exec function.

        It locates the start of the copy_exec function
        in /usr/share/initramfs-tools/hook-functions, and inserts the arch check hook
        to check the architecture of all binaries that are copied into the initramfs.

        If the arch check hook already exists, then it is not copied.

        The arch-test package must be installed for the hook to function.

        Returns:
            True if the hook was successfully installed, False otherwise.
        """

        if not os.path.isfile(self.initramfs_functions_path):
            print('hook-functions file does not exist.')
            return False

        with open(self.initramfs_functions_path, 'r') as functions_file:
            functions_lines = functions_file.read().splitlines()

        # is there a better way than using a magic string?
        if '# begin arch-check-hook' in functions_lines:
            print('arch check hook already installed.')
            return False

        shutil.copy2(self.initramfs_functions_path, self.initramfs_functions_backup_path)
        assert os.path.isfile(self.initramfs_functions_backup_path)

        with open(self.arch_check_hook_path, 'r') as arch_hook_file:
            arch_hook_lines = arch_hook_file.read().splitlines()
        for idx, line in enumerate(arch_hook_lines):
            arch_hook_lines[idx] = line.replace('TARGET_ARCH_PLACEHOLDER', self.target_arch)

        try:
            hook_index = functions_lines.index('copy_exec() {') + 1
        except ValueError:
            print('Could not find copy_exec function definition.')
            return False

        functions_lines = functions_lines[:hook_index] + arch_hook_lines + \
                          functions_lines[hook_index + 1:]
        with open(self.initramfs_functions_path, 'w') as functions_file:
            functions_file.write('\n'.join(functions_lines))

        return True

    def remove_initramfs_arch_check(self):
        """Restores the contents of hook-functions.

        This function should be called at the end of the crossgrade process.
        Currently, the hook is installed every time the Crossgrader function is created
        and removed when during in the third_stage function.

        Returns:
            True if the hook was successfully removed, False otherwise.
        """

        if not os.path.isfile(self.initramfs_functions_backup_path):
            print('Backup file does not exist.')
            return False
        if not os.path.isfile(self.initramfs_functions_path):
            print('hook-functions file does not exist.')
            return False

        shutil.copy2(self.initramfs_functions_backup_path, self.initramfs_functions_path)
        os.remove(self.initramfs_functions_backup_path)
        return True

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
        ret_code = subprocess.call(['apt-get', 'install', '-f'])
        if ret_code == 0:
            return True

        print('apt-get --fix-broken install failed.')
        print('Removing all coinstalled packages...')
        for package in packages:
            package_status_proc = subprocess.Popen(['dpkg', '-s', package],
                                                   stdout=subprocess.PIPE, stderr=sys.stderr,
                                                   universal_newlines=True)
            package_status, __ = package_status_proc.communicate()
            if 'Multi-Arch: same' not in package_status:
                continue

            # architecture should be specified for M-A: same packages
            assert ':' in package

            short_name = package[:package.index(':')]
            coinstalled = subprocess.check_output(['dpkg-query', '-f',
                                                   '${Package}:${Architecture}\n', '-W',
                                                   short_name],
                                                  universal_newlines=True).splitlines()
            for coinstalled_package in coinstalled:
                if coinstalled_package == package:
                    continue

                ret_code = subprocess.call(['dpkg', '--remove', '--force-depends',
                                            coinstalled_package])
                if ret_code == 0:
                    continue

                print('dpkg failed to remove {}.'.format(coinstalled_package))

                prerm_script = '{}.prerm'.format(coinstalled_package)
                prerm_script = os.path.join(Crossgrader.DPKG_INFO_DIR, prerm_script)

                if os.path.isfile(prerm_script):
                    print('prerm script found: {}'.format(prerm_script))
                    cont = input('Remove prerm script and try again [Y/n]? ').lower()
                    if cont == 'y' or not cont:
                        os.remove(prerm_script)
                        ret_code = subprocess.call(['dpkg', '--remove', '--force-depends',
                                                    coinstalled_package])
                        if ret_code != 0:
                            print("Couldn't remove {}.".format(coinstalled_package))

        print('Running dpkg --configure -a ...')
        ret_code = subprocess.call(['dpkg', '--configure', '-a'])
        if ret_code != 0:
            return False

        print('Running apt-get --fix-broken install...')
        ret_code = subprocess.call(['apt-get', 'install', '-f'])
        if ret_code == 0:
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

        def get_dpkg_failures(dpkg_errs):
            """Returns a tuple of (failed_debs, failed_packages) parsed from dpkg's stderr."""
            debs = set()
            packages = set()

            capture_packages = False

            for line in dpkg_errs:
                line = line.strip()

                if capture_packages:
                    if line.endswith('.deb'):
                        assert os.path.isfile(line), '{} does not exist'.format(line)
                        debs.add(line)
                    else:
                        packages.add(line)

                if line == 'Errors were encountered while processing:':
                    capture_packages = True

            return debs, packages

        # set max error count so dpkg does not abort from too many errors
        # multiply by 2 because a package can have multiple errors
        max_error_count = max(50, len(debs_to_install) * 2)

        error_count_option = '--abort-after={}'.format(max_error_count)

        proc = subprocess.Popen(['dpkg', '-i', error_count_option, *debs_to_install],
                                stdout=sys.stdout, stderr=subprocess.PIPE,
                                universal_newlines=True)
        __, __, errs = cmd_utils.tee_process(proc)

        failed_debs, failed_packages = get_dpkg_failures(errs.splitlines())

        print('Running dpkg --configure -a...')
        proc = subprocess.Popen(['dpkg', '--configure', '-a', error_count_option],
                                stdout=sys.stdout, stderr=subprocess.PIPE)
        __, __, errs = cmd_utils.tee_process(proc)

        new_failed_debs, new_failed_packages = get_dpkg_failures(errs.splitlines())
        failed_debs.update(new_failed_debs)
        failed_packages.update(new_failed_packages)

        return list(failed_debs), list(failed_packages)

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
            debs_to_install = glob(os.path.join(Crossgrader.APT_CACHE_DIR, '*.deb'))

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
            print('dpkg -i/--configure loop #{}'.format(loop_count))

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
                    print('\t{}'.format(deb))

        if debs_remaining:
            raise PackageInstallationError(debs_remaining)

        if failed_packages:
            if not Crossgrader._fix_dpkg_errors(failed_packages):
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
        unmarked = []
        for target in targets:
            target.mark_install(auto_fix=False)  # do not try to fix broken packages

            # some packages (python3-apt) refuses to mark as install for some reason
            # fetch them individually later
            if not target.marked_install:
                print(('Could not mark {} for install, '
                       'downloading binary directly.').format(target.full_name))
                unmarked.append(target)

        __, __, free_space = shutil.disk_usage(self.APT_CACHE_DIR)

        required_space = 0
        for target in unmarked:
            required_space += target.candidate.installed_size
            required_space += target.candidate.size

        for package in self._apt_cache:
            if package.marked_install:
                required_space += package.candidate.installed_size
                required_space += package.candidate.size

        if required_space > free_space:
            raise NotEnoughSpaceError(
                '{} bytes free but {} bytes required'.format(free_space, required_space)
            )

        for target in unmarked:
            target.candidate.fetch_binary(self.APT_CACHE_DIR)

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

            target_name = '{}:{}'.format(name, arch)

            try:
                package = self._apt_cache[target_name]
                if not ignore_installed or not package.is_installed:
                    packages.append(package)
            except KeyError:
                if not ignore_unavailable_targets:
                    raise PackageNotFoundError(name_with_arch)
                else:
                    print("Couldn't find {}, ignoring...".format(name_with_arch))

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
                                                universal_newlines=True).splitlines()
        for hook_package in hook_packages:
            name, hook = hook_package.split(': ')

            if hook not in unaccounted_hooks:
                print('Expected {} to contain an initramfs hook, but it does not.'.format(name))
                print('Skipping.')
                continue

            unaccounted_hooks.remove(hook)

            package = self._apt_cache[name]

            if not package.is_installed:
                print(('WARNING: {}, containing an initramfs hook, '.format(package),
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
                                                      '-W'], universal_newlines=True).splitlines()

        for full_name in installed_packages:
            package = self._apt_cache[full_name]
            if self._is_first_stage_target(package):
                targets.add(package.shortname)

        # if python-apt is not crossgraded, it will not find any packages other than
        # its own architecture/installed packages
        targets.add('python3-apt')
        targets.add('python3')

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
                                                      '-W'], universal_newlines=True).splitlines()
        for full_name in installed_packages:
            package = self._apt_cache[full_name]

            if not package.is_installed:
                continue

            if package.installed.architecture not in ('all', self.target_arch):
                targets.add(package.shortname)

        return self.find_packages_from_names(targets, ignore_unavailable_targets)

    @staticmethod
    def get_arch_packages(foreign_arch):
        """Returns all the packages in the given architecture."""
        installed_packages = subprocess.check_output(['dpkg-query', '-f',
                                                      '${Package}:${Architecture}\n',
                                                      '-W'], universal_newlines=True).splitlines()

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

        print('{} targets found.'.format(len(targets)))
        for pkg_name in sorted(map(lambda pkg: pkg.fullname, targets)):
            print(pkg_name)

        if args.dry_run:
            return

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

        print('{} targets found.'.format(len(targets)))

        if args.dry_run:
            return

        cont = input('Do you want to continue [y/N]? ').lower()
        if cont == 'y':
            crossgrader.cache_package_debs(targets)

            if not args.download_only:
                crossgrader.install_packages()
        else:
            print('Aborted')


def third_stage(args):
    """Runs the third stage of the crossgrading process.

    Removes all packages from the given architecture, excluding ones contained by args.packages.
    """
    with Crossgrader(args.target_arch) as crossgrader:
        foreign_arch = args.third_stage
        targets = crossgrader.get_arch_packages(foreign_arch)

        if args.packages:
            targets = [pkg_name for pkg_name in targets if pkg_name not in args.packages]

        print('{} targets found.'.format(len(targets)))
        for pkg_name in sorted(targets):
            print(pkg_name)

        cont = input('Do you want to continue [y/N]? ').lower()

        if args.dry_run:
            return

        if cont == 'y':
            subprocess.check_call(['dpkg', '--purge', *targets])
            remaining = crossgrader.get_arch_packages(foreign_arch)
            if remaining:
                print('The following packages could not be successfully purged:')
                for pkg_name in remaining:
                    print('\t{}'.format(pkg_name))
            else:
                print('All targets successfully purged.')
                print(('If desired, run dpkg --remove-architecture {} '
                       'to complete the crossgrade.').format(foreign_arch))

            print('Removing initramfs binary architecture check hook...')
            if crossgrader.remove_initramfs_arch_check():
                print('Hook successfully removed.')
            else:
                print('Hook could not be removed.')


def install_from(args):
    """Installs all .debs from the specified location."""
    with Crossgrader(args.target_arch) as crossgrader:
        debs = glob(os.path.join(args.install_from, '*.deb'))
        print('Installing the following .debs:')
        for deb in debs:
            print('\t{}'.format(deb))

        if args.dry_run:
            return

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
                              '(default: {}), but not package listing '
                              'and download').format(Crossgrader.APT_CACHE_DIR),
                        nargs='?', const=Crossgrader.APT_CACHE_DIR)
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
                        help=('Crossgrade the subsequent package names and nothing else. '
                              'If used with --third-stage, the subsequent packages will '
                              'be excluded from removal'),
                        nargs='+')
    parser.add_argument('--dry-run',
                        help='Run the crossgrader, but do not change anything',
                        action='store_true')
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
