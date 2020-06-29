"""Checks if your installed packages were all successfully crossgraded."""

import os
import subprocess
import sys

def save_package_list(output_file):
    """Saves your currently installed packages to the given file path."""
    print('Saving currently installed packages...')
    assert not os.path.isfile(output_file)

    package_info = subprocess.check_output(['dpkg-query', '-f',
                                            '${Package}\t${Architecture}\t${Status}\n', '-W'],
                                           text=True)

    with open(output_file, 'w') as packages_file:
        packages_file.write(package_info)


def package_list_to_dict(contents):
    """Returns a dict version of a list containing package information.

    Each entry should be in the form Package\tArchitecture\tStatus.
    """
    packages = {}
    for package_info in contents:
        name, arch, status = package_info.split()
        packages[f'{name}:{arch}'] = status

    return packages


def compare_package_list(input_file):
    """Compares your installed packages to list in the given file."""
    assert os.path.isfile(input_file)

    curr_arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True)

    curr_packages = subprocess.check_output(['dpkg-query', '-f',
                                             '${Package}\t${Architecture}\t${Status}\n', '-W'],
                                            text=True).splitlines()
    curr_packages = package_list_to_dict(curr_packages)

    with open(input_file, 'r') as packages_file:
        old_packages = package_list_to_dict(packages_file.read().splitlines())

    for package, status in old_packages.items():
        name, arch = package.split(':')

        if status != 'install ok installed':
            continue

        target_package = package if arch == 'all' else f'{name}:{curr_arch}'

        if target_package not in curr_packages:
            found = False
        else:
            found = target_package[package] == 'install ok installed'

        if not found:
            print(f'{target_package} is not installed in the target arch.', file=sys.stderr)


def main():
    """Main function of the script"""
    out_file = 'packages.txt'
    script_dir = os.path.dirname(__file__)

    file_name = os.path.join(script_dir, out_file)

    if not os.path.isfile(file_name):
        save_package_list(file_name)
    else:
        compare_package_list(file_name)


if __name__ == '__main__':
    main()
