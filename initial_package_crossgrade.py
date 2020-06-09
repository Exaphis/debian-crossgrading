import argparse
from collections import defaultdict
from glob import glob
import os
import subprocess
import sys


def crossgrade(targets):
    """Crossgrades each package listed in targets

    :param targets: list of packages to crossgrade
    """


    def install_packages(packages_to_install):
        # unfeasible to perform a topological sort (complex/circular dependencies, etc.)
        # easier to install/reconfigure repeatedly until errors resolve themselves
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
                print('The following packages remain not fully installed:')
                for remaining in packages_remaining:
                    print(f'\t{remaining}')
        else:
            print('All .debs were installed.')


    # clean apt-get cache (/var/cache/apt/archives)
    subprocess.check_call(['apt-get', 'clean'])

    # call apt to cache .debs for package and dependencies
    # download one at a time to prevent apt from complaining due
    # to not being able to resolve breakages
    for target in targets:
        subprocess.check_call(['apt-get', '--download-only', 'install', target, '-y'],
                              stdout=sys.stdout, stderr=sys.stderr)

    # crossgrade in one call to prevent repeat triggers
    # (e.g. initramfs rebuild), which saves time

    # use dpkg to perform the crossgrade
    # (why? apt doesn't support crossgrading whereas dpkg does, unsure if this is up-to-date)
    # https://lists.debian.org/debian-devel-announce/2012/03/msg00005.html

    # install all at once
    # installing libraries before others doesn't bring much time savings because packages like
    # libgcc1 depend on gcc-8-base, which is not a library
    install_packages(glob('/var/cache/apt/archives/*.deb'))


parser = argparse.ArgumentParser()
parser.add_argument('target_arch', help='Target architecture of the crossgrade')
parser.add_argument('-s', '--simulate', help='No action; perform a simulation of what would happen',
                    action='store_true')
args = parser.parse_args()

CURRENT_ARCH = subprocess.check_output(['dpkg', '--print-architecture'], encoding='UTF-8')
TARGET_ARCH = args.target_arch

packages = subprocess.check_output(['dpkg-query', '-f',
                                    '${Package}\t${Architecture}\t${Status}\t' \
                                    '${Priority}\t${Essential}\n',
                                    '-W'], encoding='UTF-8').splitlines()

# dict of package info containing keyed by full name (name:arch)
package_info = {}

# keep a list of candidates for each package name (a package may be in multiple archs)
package_candidates = defaultdict(list)

for package in packages:
    name, arch, status, priority, is_essential = package.split('\t')
    full_name = f'{name}:{arch}'
    package_info[full_name] = {'name': name,
                               'arch': arch,
                               'status': status,
                               'priority': priority,
                               'is_essential': is_essential == 'yes'}
    package_candidates[name].append(full_name)

crossgrade_targets = set()

# crossgrade all packages with initramfs hooks scripts so boot can succeed
unaccounted_hooks = set(glob('/usr/share/initramfs-tools/hooks/*'))
hook_packages = subprocess.check_output(['dpkg-query', '-S',
                                         '/usr/share/initramfs-tools/hooks/*'],
                                        encoding='UTF-8').splitlines()
for package in hook_packages:
    name, hook = package.split(': ')

    unaccounted_hooks.discard(hook)

    # TODO: what does dpkg output if the same package is installed twice
    # with different architectures?
    # current assumption: it outputs both as name:arch
    if ':' in name:
        full_name = name
        name = name[:name.index(':')]
    else:
        full_name = package_candidates[name][0]

    if package_info[full_name]['arch'] not in ('all', TARGET_ARCH):
        crossgrade_targets.add(f'{name}:{TARGET_ARCH}')

# crossgrade all Priority: required packages to be able to finish crossgrade after reboot
for package, info in package_info.items():
    if info['priority'] == 'required' and info['arch'] not in ('all', TARGET_ARCH):
        crossgrade_targets.add(f'{info["name"]}:{TARGET_ARCH}')

if len(unaccounted_hooks) > 0:
    print('The following hooks in /usr/share/initramfs-tools/hooks are unaccounted for:')
    for hook in unaccounted_hooks:
        print(f'\t{hook}')
    print('Aborting crossgrade.')
else:
    print(f'{len(crossgrade_targets)} targets found.')
    print(crossgrade_targets)

    if not args.simulate:
        cont = input('Do you want to continue [Y/n]? ').lower()
        if cont in ('', 'y'):
            crossgrade(crossgrade_targets)
        else:
            print('Aborted.')
