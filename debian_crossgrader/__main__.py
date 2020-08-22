"""crossgrader entrypoint"""
import os
from glob import glob
import subprocess
import argparse
import shutil

from debian_crossgrader.crossgrader import Crossgrader
from debian_crossgrader.utils import apt as apt_utils

def first_stage(args):
    """Runs first stage of the crossgrade process.

    Installs initramfs packages and packages with Priority: required/important.
    Does not need to be run if the target architecture can run the existing architecture.
    """
    with Crossgrader(args.target_arch) as crossgrader:
        if args.packages:
            targets = crossgrader.find_package_objs(args.packages, default_arch=args.target_arch)
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
            # cache qemu debs first because internet access might go down
            # after crossgrade
            # crossgrade qemu just if qemu-user-static exists for any arch
            # pairs that can be run on the current arch but the current can't
            # be run on the foreign arch
            qemu_path_exists = os.path.isdir(crossgrader.qemu_deb_path)
            crossgrade_qemu = crossgrader.qemu_installed or crossgrader.non_supported_arch
            if crossgrade_qemu and not qemu_path_exists:
                print('Saving qemu-user-static debs for second stage...')
                qemu_pkgs = crossgrader.find_package_objs(['qemu-user-static', 'binfmt-support'],
                                                          default_arch=args.target_arch)
                crossgrader.cache_package_debs(qemu_pkgs, crossgrader.qemu_deb_path)
                print('qemu-user-static saved.')

            if args.download_only:
                crossgrader.cache_package_debs(targets)
            else:
                # crossgrade dpkg/apt for correct crossgrading of Architecture: all packages that
                # aren't marked M-A: foreign
                pkg_packages = crossgrader.find_package_objs(
                    ['dpkg', 'apt', 'python3', 'python3-apt'],
                    default_arch=args.target_arch
                )

                if not all(pkg.is_installed for pkg in pkg_packages):
                    crossgrader.cache_package_debs(pkg_packages)
                    crossgrader.install_packages(fix_broken=False)

                    # Force restart of the crossgrader so new version of python3
                    # and python3-apt is used
                    print('Crossgraded dpkg, apt, python3, and python3-apt.')
                    print('Please re-run the first stage to continue the crossgrade.')
                    return

                crossgrader.cache_package_debs(targets)
                # fix_broken should be disabled for first stage so apt doesn't
                # decide to uninstall some necessary packages
                crossgrader.install_packages(fix_broken=False)
                subprocess.call(['update-initramfs', '-u', '-k', 'all'])
        else:
            print('Aborted.')


def second_stage(args):
    """Runs the second stage of the crossgrade process.

    Crossgrades all packages that are not in the target architecture.
    """
    with Crossgrader(args.target_arch) as crossgrader:
        # crossgrade qemu-user-static first to prevent list_second_stage_targets
        # from finding it
        if os.path.isdir(crossgrader.qemu_deb_path):
            print('qemu-user-static must be crossgraded.')
            if not args.dry_run:
                cont = input('Do you want to continue [y/N]? ').lower()
                if cont == 'y':
                    print('Crossgrading saved qemu-user-static...')
                    crossgrader.install_packages(
                        glob(os.path.join(crossgrader.qemu_deb_path, '*.deb')),
                        fix_broken=False
                    )
                    os.rmdir(crossgrader.qemu_deb_path)
                    print('qemu-user-static successfully crossgraded.')
            else:
                print('qemu-user-static crossgrade skipped.')

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
        foreign_arch = args.third_stage[0]
        targets = apt_utils.get_arch_packages(foreign_arch)
        if args.packages:
            targets = [pkg_name for pkg_name in targets if pkg_name not in args.packages]

        print('{} targets found.'.format(len(targets)))
        for pkg_name in sorted(targets):
            print(pkg_name)

        cont = input('Do you want to continue [y/N]? ').lower()

        if args.dry_run:
            return

        if cont == 'y':
            subprocess.check_call(['dpkg', '--purge'] + targets)
            remaining = apt_utils.get_arch_packages(foreign_arch)
            if args.packages:
                remaining = [pkg_name for pkg_name in remaining if pkg_name not in args.packages]

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


def cleanup():
    """Cleans up any extra files, namely Crossgrader's storage_dir"""
    if os.path.isdir(Crossgrader.storage_dir):
        shutil.rmtree(Crossgrader.storage_dir)
        print('crossgrader data folder removed.')
    else:
        print('crossgrader data folder did not exist.')

    print('Removing initramfs binary architecture check hook...')
    if Crossgrader.remove_initramfs_arch_check():
        print('Hook successfully removed.')
    else:
        print('Hook could not be removed.')


def main():
    """Crossgrade driver"""
    parser = argparse.ArgumentParser()
    parser.add_argument('target_arch', help='Target architecture of the crossgrade')
    parser.add_argument('--second-stage',
                        help=('Run the second stage of the crossgrading process '
                              '(crossgrading all remaining packages)'),
                        action='store_true')
    parser.add_argument('--third-stage',
                        help=('Run the third stage of the crossgrading process '
                              '(removing all packages under specified arch)'),
                        metavar='OLD_ARCH', nargs=1)
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
    parser.add_argument('--cleanup',
                        help=('Clean up any extra files stored by the crossgrader. '
                              'The given architecture will be ignored.'),
                        action='store_true')
    args = parser.parse_args()

    if args.force_all:
        args.force_initramfs = True
        args.force_unavailable = True

    if args.cleanup:
        cleanup()
    elif args.install_from:
        install_from(args)
    elif args.second_stage:
        second_stage(args)
    elif args.third_stage:
        third_stage(args)
    else:
        first_stage(args)

# __name_ is debian_crossgrader.__main__ usually, __main__ if
# called with -m flag

# include __main__ guard to prevent main() from being called twice from console
# script entrypoint
if __name__ == '__main__':
    main()
