"""Tool to install a given number of random packages from dpkg."""
import argparse
import random

import apt
import apt.progress

def install_random(num_packages, choice_func=None):
    """Install a given number of random packages, not including dependencies.

    If choice_func is specified, only packages that make choice_func return True
    are considered.
    """
    cache = apt.cache.Cache()

    candidates = []
    for package in cache.keys():
        package_obj = cache[package]
        if package_obj.is_installed:
            continue
        if choice_func is not None and not choice_func(package_obj):
            continue

        candidates.append(package)

    while num_packages > 0:
        choice_idx = random.randrange(len(candidates))
        package = candidates.pop(choice_idx)

        cache[package].mark_install()
        if cache[package].marked_install:
            print(f'{package} marked for install')
            num_packages -= 1

    cache.commit(apt.progress.TextFetchProgress(),
                 apt.progress.InstallProgress())


def main():
    """Main function"""
    parser = argparse.ArgumentParser()
    parser.add_argument('num_packages',
                        help='The number of random packages that should be installed',
                        type=int)
    args = parser.parse_args()

    install_random(args.num_packages)


if __name__ == '__main__':
    main()
