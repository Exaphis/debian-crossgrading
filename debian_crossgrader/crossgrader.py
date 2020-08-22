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


from glob import glob
import os
import shutil
import subprocess
import sys
import traceback

import appdirs
import apt

from debian_crossgrader.utils import apt as apt_utils
from debian_crossgrader.utils import cmd as cmd_utils
from debian_crossgrader.utils import shells as shells_utils


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


class Crossgrader:
    """Finds packages to crossgrade and crossgrades them.

    Instance attributes:
        target_arch: A string representing the target architecture of dpkg.
        current_arch: A string representing the current architecture of dpkg.
        non_supported_arch: A boolean indicating whether the target arch is natively supported
            by the current CPU.
        qemu_installed: A boolean indicated whether or not qemu-user-static is installed.

        _apt_cache: python3-apt cache

    Class attributes:
        initramfs_functions_backup_path: Path to the backup of hook-functions.
        arch_check_hook_path: Path to the arch-check-hook.sh shell script.
        qemu_deb_path: Path to a directory containing temporary cached qemu debs.

    """

    APT_CACHE_DIR = '/var/cache/apt/archives'
    DPKG_INFO_DIR = '/var/lib/dpkg/info'
    INITRAMFS_FUNCTIONS_PATH = '/usr/share/initramfs-tools/hook-functions'

    ARCH_CHECK_HOOK_NAME = 'arch-check-hook.sh'
    INITRAMFS_FUNCTIONS_BACKUP_NAME = 'hook-functions.bak'
    QEMU_DEB_DIR_NAME = 'qemu-debs'

    APP_NAME = 'debian_crossgrader'
    storage_dir = appdirs.site_data_dir(APP_NAME)

    FALLBACK_CROSSGRADER_DEPENDENCIES = ['python3', 'python3-apt']

    # qemu_deb_path will be filled w/ qemu-user-static debs if self.non_supported_arch == True
    # during first stage
    # if it exists, its debs will be installed before second stage
    qemu_deb_path = os.path.join(storage_dir, QEMU_DEB_DIR_NAME)
    initramfs_functions_backup_path = os.path.join(storage_dir, INITRAMFS_FUNCTIONS_BACKUP_NAME)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    arch_check_hook_path = os.path.join(script_dir, ARCH_CHECK_HOOK_NAME)

    def __init__(self, target_architecture):
        """Inits Crossgrader with the given target architecture.

        Raises:
            InvalidArchitectureError: The given target_architecture is not recognized
                by dpkg.
        """

        # set LC_ALL=C so we can rely on command output being English
        os.environ['LC_ALL'] = 'C'

        try:
            os.makedirs(self.storage_dir, exist_ok=True)
        except PermissionError:
            raise PermissionError('crossgrader: must be superuser.')

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

        arch_test_ret = subprocess.call(['arch-test', '-n', self.target_arch],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if arch_test_ret != 0:
            if arch_test_ret == 2:
                # no need to throw an error here, qemu-user-static should be able to handle it
                print(('arch-test lacks a helper for {}; assuming not supported on this machine '
                       'but runnable with emulation.').format(self.target_arch))
            elif arch_test_ret == 1:
                # ensure target arch can be run with emulation for foreign package setup
                support_with_emu = subprocess.call(['arch-test', self.target_arch],
                                                   stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL) == 0
                if not support_with_emu:
                    raise InvalidArchitectureError(
                        ('Architecture {} is not runnable on this machine. Please install '
                         'qemu-user-static and try again.').format(self.target_arch)
                    )
            else:
                raise CrossgradingError('Ensure arch-test is installed.')

            self.non_supported_arch = True
        else:
            self.non_supported_arch = False

        if self.non_supported_arch:
            print(('Architecture {} is not natively supported '
                   'on the current machine.').format(self.target_arch))

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

        self.qemu_installed = self._apt_cache['qemu-user-static'].is_installed

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

        if not os.path.isfile(self.INITRAMFS_FUNCTIONS_PATH):
            print('hook-functions file does not exist.')
            return False

        with open(self.INITRAMFS_FUNCTIONS_PATH, 'r') as functions_file:
            functions_lines = functions_file.read().splitlines()

        # is there a better way than using a magic string?
        if '# begin arch-check-hook' in functions_lines:
            print('arch check hook already installed.')
            return False

        shutil.copy2(self.INITRAMFS_FUNCTIONS_PATH, self.initramfs_functions_backup_path)
        assert os.path.isfile(self.initramfs_functions_backup_path)
        print('Backed up hook-functions to {}'.format(self.initramfs_functions_backup_path))

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
        with open(self.INITRAMFS_FUNCTIONS_PATH, 'w') as functions_file:
            functions_file.write('\n'.join(functions_lines))

        return True

    @staticmethod
    def remove_initramfs_arch_check():
        """Restores the contents of hook-functions.

        This function should be called at the end of the crossgrade process.
        Currently, the hook is installed every time the Crossgrader function is created
        and removed when during in the third_stage function.

        Returns:
            True if the hook was successfully removed, False otherwise.
        """

        if not os.path.isfile(Crossgrader.INITRAMFS_FUNCTIONS_PATH):
            print('hook-functions file does not exist.')
            return False

        if not os.path.isfile(Crossgrader.initramfs_functions_backup_path):
            print('Backup file does not exist.')
            return False

        with open(Crossgrader.INITRAMFS_FUNCTIONS_PATH, 'r') as functions_file:
            functions_lines = functions_file.read().splitlines()

        if '# begin arch-check-hook' not in functions_lines:
            print('arch check hook not installed.')
            return False

        shutil.copy2(Crossgrader.initramfs_functions_backup_path,
                     Crossgrader.INITRAMFS_FUNCTIONS_PATH)
        os.remove(Crossgrader.initramfs_functions_backup_path)
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

        if not packages:
            return True

        print('Running apt-get --fix-broken install...')
        # let user select yes/no
        ret_code = subprocess.call(['apt-get', 'install', '-f', '-y'])
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

                # this triggers lintian: uses-dpkg-database-directly,
                # but is necessary to handle crossgrading
                # packages like python3-pil and python3-cairo
                # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=810551
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

        proc = subprocess.Popen(['dpkg', '-i', error_count_option] + debs_to_install,
                                stdout=sys.stdout, stderr=subprocess.PIPE,
                                universal_newlines=True)
        __, __, errs = cmd_utils.tee_process(proc)

        failed_debs, failed_packages = get_dpkg_failures(errs.splitlines())

        print('Running dpkg --configure -a...')
        proc = subprocess.Popen(['dpkg', '--configure', '-a', error_count_option],
                                stdout=sys.stdout, stderr=subprocess.PIPE,
                                universal_newlines=True)
        __, __, errs = cmd_utils.tee_process(proc)

        new_failed_debs, new_failed_packages = get_dpkg_failures(errs.splitlines())
        failed_debs.update(new_failed_debs)
        failed_packages.update(new_failed_packages)

        return list(failed_debs), list(failed_packages)

    @staticmethod
    def _install_configure_loop(debs_to_install):
        """
        Repeatedly runs _install_and_configure until all .debs are installed or
        failures stop decreasing.

        Args:
            debs_to_install: A list of paths to .deb files.

        Returns:
            A list of packages that were not successfully installed.

        Raises:
            PackageInstallationError: Some of the packages were not successfully
                installed/configured.
        """
        # unfeasible to perform a topological sort (complex/circular dependencies, etc.)
        # easier to install/reconfigure repeatedly until errors resolve themselves

        # use dpkg to perform the crossgrade because apt does not realize that crossgrading
        # a package will not necessarily break it because of qemu user emulation
        # e.g. apt refuses to install perl-base

        # crossgrade in one call to prevent repeat triggers
        # (e.g. initramfs rebuild), saving time

        # https://blog.zugschlus.de/archives/972-How-to-amd64-an-i386-Debian-installation-with-multiarch.html#c24572
        # Summary: Use dpkg --unpack; dpkg --configure --pending instead of dpkg -i?
        # dpkg --unpack still gets stuck because of various pre-depends

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
                raise PackageInstallationError(failed_debs)

            debs_remaining = failed_debs

            if debs_remaining:
                print('The following .deb files were not fully installed, retrying...')
                for deb in debs_remaining:
                    print('\t{}'.format(deb))

        return failed_packages

    @staticmethod
    def install_packages(debs_to_install=None, fix_broken=True):
        """Installs specified .deb files.

        Installs the .deb files specified in packages_to_install
        using a looping dpkg -i *.deb / dpkg --configure -a.

        Args:
            debs_to_install: A list of paths to .deb files. If it is None,
                all .debs in APT's cache will be installed.
            fix_broken: If true, try to fix any dpkg errors after installation.

        Raises:
            PackageInstallationError: Some of the packages were not successfully
                installed/configured.
        """
        if debs_to_install is None:
            debs_to_install = glob(os.path.join(Crossgrader.APT_CACHE_DIR, '*.deb'))

        # find all packages marked as autoinstalled, and match them to the newly installed ones
        # apt-mark shows packages in native architecture without colon and others with
        print('Parsing automatically installed packages...')
        proc = subprocess.Popen(['apt-mark', 'showauto'], stdout=subprocess.PIPE,
                                universal_newlines=True)
        auto_pkgs_list, __ = proc.communicate()
        auto_pkgs_list = auto_pkgs_list.splitlines()

        ret_code = proc.returncode
        assert ret_code == 0, 'apt-mark showauto failed with code {}'.format(ret_code)

        # to handle packages installed in non-native architectures
        # (e.g. all native packages during second stage), strip all architectures from the
        # packages returned by apt-mark
        # therefore, if any existing package with the same name is auto-installed,
        # then the newly installed one will be auto-installed as well
        auto_pkgs = set()
        for pkg in auto_pkgs_list:
            try:
                auto_pkgs.add(pkg[:pkg.index(':')])
            except ValueError:
                auto_pkgs.add(pkg)

        # must find such packages before they are installed because dpkg -i will re-mark
        # them as manually installed
        mark_auto_pkgs = []
        for deb in debs_to_install:
            proc = subprocess.Popen(
                ['dpkg-deb', '--showformat=${Package}:${Architecture}', '-W', deb],
                stdout=subprocess.PIPE, universal_newlines=True
            )
            pkg_full_name, __ = proc.communicate()

            ret_code = proc.returncode
            assert ret_code == 0, 'dpkg-deb failed with code {}'.format(ret_code)

            pkg_short_name = pkg_full_name[:pkg_full_name.index(':')]
            if pkg_short_name in auto_pkgs:
                mark_auto_pkgs.append(pkg_full_name)
        print('...done')

        failed_packages = Crossgrader._install_configure_loop(debs_to_install)

        if fix_broken and not Crossgrader._fix_dpkg_errors(failed_packages):
            print('Some dpkg errors could not be fixed automatically.')

        print('Re-marking packages as auto-installed...')
        ret_code = subprocess.call(['apt-mark', 'auto'] + mark_auto_pkgs,
                                   stdout=subprocess.DEVNULL)
        print('...done')

    def cache_package_debs(self, targets, target_dir=None):
        """Cache specified packages.

        Clears APT's .deb cache, then downloads specified packages
        to /var/apt/cache/archives or the given target_dir using python-apt.

        Args:
            targets: A list of apt.package.Package objects to crossgrade.
            target_dir: If target_dir set, move all cached .debs the given directory.
        """


        # clean /var/cache/apt/archives for download
        # is there a python-apt function for this?
        subprocess.check_call(['apt-get', 'clean'])

        # use python-apt to cache .debs for package and dependencies
        # because apt-get --download-only install will not download
        # if it can't find a good way to resolve dependencies
        for target in targets:
            if target.is_installed:
                continue

            target.mark_install(auto_fix=False)  # do not try to fix broken packages

            # some packages (python3-apt) refuses to mark as install for some reason
            if not target.marked_install:
                print(('Could not mark {} for install, '
                       'fixing manually.').format(target.fullname))
                target.mark_install(auto_fix=False, auto_inst=False)
                assert target.marked_install, \
                       '{} not marked as install despite no auto_inst'.format(target.fullname)

        __, __, free_space = shutil.disk_usage(self.APT_CACHE_DIR)

        required_space = 0
        for package in self._apt_cache:
            if package.marked_install:
                required_space += package.candidate.installed_size
                required_space += package.candidate.size

        if required_space > free_space:
            raise NotEnoughSpaceError(
                '{} bytes free but {} bytes required'.format(free_space, required_space)
            )

        # fetch_archives() throws a more detailed error if a specific package
        # could not be downloaded for some reason.
        # Do not check its return value; it is undefined.
        self._apt_cache.fetch_archives()

        self._apt_cache.clear()

        if target_dir is not None:
            os.makedirs(target_dir, exist_ok=True)

            for deb in glob(os.path.join(Crossgrader.APT_CACHE_DIR, '*.deb')):
                shutil.move(deb, target_dir)

    def find_package_objs(self, names, **kwargs):
        """Wrapper for debian_crossgrader.utils.apt's find_package_objs,
        passing in the instance's cache."""
        return apt_utils.find_package_objs(names, self._apt_cache, **kwargs)


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

    def _get_initramfs_hook_packages(self, ignore_initramfs_remnants=False):
        """Returns a set of packages shortnames that contain initramfs hooks.

        Raises:
            RemnantInitramfsHooksError: Some initramfs hooks could not be matched with a package.
        """
        out_names = set()

        unaccounted_hooks = set(glob('/usr/share/initramfs-tools/hooks/*'))
        hook_pkgs = apt_utils.iter_packages_containing_files(
            self._apt_cache, '/usr/share/initramfs-tools/hooks/*'
        )

        for package, hook_file in hook_pkgs:
            if hook_file not in unaccounted_hooks:
                print(('Expected {} to contain an initramfs hook, '
                       'but it does not.').format(package.fullname))
                print('Skipping.')
                continue

            unaccounted_hooks.discard(hook_file)

            if not package.is_installed:
                print(('WARNING: {}, containing an initramfs hook, '
                       'is marked as not fully installed.').format(package))
                print('Assuming it is installed.')
                architecture = package.candidate.architecture
            else:
                architecture = package.installed.architecture

            if architecture not in ('all', self.target_arch):
                out_names.add(package.shortname)

        if unaccounted_hooks and not ignore_initramfs_remnants:
            raise RemnantInitramfsHooksError(unaccounted_hooks)

        return out_names

    def list_first_stage_targets(self, ignore_initramfs_remnants=False,
                                 ignore_unavailable_targets=False):
        """Returns a list of apt.package.Package objects that must be crossgraded before reboot.

        Retrieves and returns a list of all packages with Priority: required/important,
        packages with installed initramfs hooks, packages for login shells, and crossgrader
        dependencies.

        Args:
            ignore_initramfs_remnants: If true, do not raise a RemnantInitramfsHooksError if
                there are initramfs hooks that could not be linked.
            ignore_unavailable_targets: If true, do not raise a PackageNotFoundError if a package
                could not be found in the target architecture.

        Raises:
            RemnantInitramfsHooksError: Some initramfs hooks could not be matched with a package.
            PackageNotFoundError: A required package in the target architecture was not available
                in APT's cache.
        """

        targets = {pkg.shortname for pkg in apt_utils.iter_package_objs(self._apt_cache)
                   if self._is_first_stage_target(pkg)}
        targets |= self._get_initramfs_hook_packages(ignore_initramfs_remnants)

        # crossgrade crossgrader dependencies
        # if python-apt is not crossgraded, it will not find any packages other than
        # its own architecture/installed packages
        try:
            crossgrader_pkg = self._apt_cache['crossgrader']
        except KeyError:
            # fallback if not installed as package or package doesn't exist
            targets.update(self.FALLBACK_CROSSGRADER_DEPENDENCIES)
        else:
            if not crossgrader_pkg.is_installed:
                targets.update(self.FALLBACK_CROSSGRADER_DEPENDENCIES)
            else:
                for dep in crossgrader_pkg.installed.dependencies:
                    targets.update(ver.package.shortname for ver in dep.installed_target_versions
                                   if ver.architecture not in ('all', self.target_arch))

        # crossgrade all available login shells
        # if login shell is not crossgrader and isn't priority: required (e.g. zsh), then the user
        # cannot login
        shells = shells_utils.list_shells()
        for package, __ in apt_utils.iter_packages_containing_files(self._apt_cache, *shells):
            if not package.is_installed:
                print(('WARNING: {}, containing a login shell, '
                       'is marked as not fully installed.').format(package))
                print('Assuming it is installed.')
                architecture = package.candidate.architecture
            else:
                architecture = package.installed.architecture

            if architecture not in ('all', self.target_arch):
                targets.add(package.shortname)

        targets.add('sudo')

        return self.find_package_objs(targets, default_arch=self.target_arch,
                                      ignore_unavailable_targets=ignore_unavailable_targets,
                                      ignore_installed=True)

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
        for pkg in apt_utils.iter_package_objs(self._apt_cache):
            if not pkg.is_installed:
                continue

            if pkg.installed.architecture not in ('all', self.target_arch):
                targets.add(pkg.shortname)

        return self.find_package_objs(targets, default_arch=self.target_arch,
                                      ignore_unavailable_targets=ignore_unavailable_targets,
                                      ignore_installed=True)
