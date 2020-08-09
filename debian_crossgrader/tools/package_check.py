"""Checks if your installed packages were all successfully crossgraded."""

import argparse
import os
import shutil
import subprocess
import sys

import appdirs

def save_package_list(output_file):
    """Saves your currently installed packages to the given file path."""
    print('Saving currently installed packages...')
    assert not os.path.isfile(output_file)

    package_info = subprocess.check_output(['dpkg-query', '-f',
                                            '${Package}\t${Architecture}\t${Status}\n', '-W'],
                                           universal_newlines=True)

    with open(output_file, 'w') as packages_file:
        packages_file.write(package_info)

    print('Packages saved.')

def package_list_to_dict(contents):
    """Returns a dict version of a list containing package information.

    Each entry should be in the form Package\tArchitecture\tStatus.
    """
    packages = {}
    for package_info in contents:
        name, arch, status = package_info.split('\t')
        packages['{}:{}'.format(name, arch)] = status

    return packages


def compare_package_list(input_file):
    """Compares your installed packages to list in the given file."""
    assert os.path.isfile(input_file)

    curr_arch = subprocess.check_output(['dpkg', '--print-architecture'],
                                        universal_newlines=True).strip()

    curr_packages = subprocess.check_output(['dpkg-query', '-f',
                                             '${Package}\t${Architecture}\t${Status}\n', '-W'],
                                            universal_newlines=True).splitlines()
    curr_packages = package_list_to_dict(curr_packages)

    with open(input_file, 'r') as packages_file:
        old_packages = package_list_to_dict(packages_file.read().splitlines())

    for package, status in old_packages.items():
        name, arch = package.split(':')

        if status != 'install ok installed':
            continue

        target_package = package if arch == 'all' else '{}:{}'.format(name, curr_arch)

        if target_package not in curr_packages:
            found = False
        else:
            found = curr_packages[target_package] == 'install ok installed'

        if not found:
            print('{} is not installed in the target arch.'.format(target_package),
                  file=sys.stderr)


def main():
    """Main function of the script"""
    parser = argparse.ArgumentParser(
        description='Checks if your installed packages were all successfully crossgraded.'
    )
    parser.add_argument('--cleanup', action='store_true',
                        help=('Remove any package checker data. Next time the checker is run, '
                              'the package list will be regenerated.'))
    args = parser.parse_args()

    app_name = 'debian_crossgrader_package_check'
    storage_dir = appdirs.site_data_dir(app_name)

    if args.cleanup:
        if os.path.isdir(storage_dir):
            shutil.rmtree(storage_dir)
            print('package_check data folder removed.')
        else:
            print('package_check data folder did not exist.')
    else:
        out_file = 'packages.txt'
        os.makedirs(storage_dir, exist_ok=True)

        file_name = os.path.join(storage_dir, out_file)

        if not os.path.isfile(file_name):
            save_package_list(file_name)
        else:
            compare_package_list(file_name)


if __name__ == '__main__':
    main()
