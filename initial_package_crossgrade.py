from collections import defaultdict
from glob import glob
import subprocess
import sys


def crossgrade(targets):
    # clean apt-get cache (/var/cache/apt/archives)
    subprocess.check_call(['apt-get', 'clean'])

    # call apt to cache .debs for package and dependencies
    subprocess.check_call(['apt-get', '--download-only', 'install', *targets, '-y'],
                          stdout=sys.stdout, stderr=sys.stderr)

    # crossgrade in one dpkg call to prevent repeat triggers
    # (e.g. initramfs rebuild), which saves time

    # use dpkg to perform the crossgrade
    # (why? apt doesn't support crossgrading whereas dpkg does, unsure if this is up-to-date)
    # https://lists.debian.org/debian-devel-announce/2012/03/msg00005.html

    # use the --force-depends option to avoid having to topologically

    # sort the packages to see which to install first based on dependencies
    subprocess.check_call(['dpkg', '-i', '--force-depends', '/var/cache/apt/archives/*.deb'],
                          stdout=sys.stdout, stderr=sys.stderr)

CURRENT_ARCH = subprocess.check_output(['dpkg', '--print-architecture'], encoding='UTF-8')
TARGET_ARCH = 'arm64'

packages = subprocess.check_output(['dpkg-query', '-f',
                                    '${Package}\t${Architecture}\t${Status}\t${Essential}\n',
                                    '-W'], encoding='UTF-8').splitlines()

# dict of package info containing keyed by full name (name:arch)
package_info = {}

# keep a list of candidates for each package name (a package may be in multiple archs)
package_candidates = defaultdict(list)

for package in packages:
    name, arch, status, is_essential = package.split('\t')
    full_name = f'{name}:{arch}'
    package_info[full_name] = {'name': name,
                               'arch': arch,
                               'status': status,
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
    else:
        full_name = package_candidates[name][0]

    if package_info[full_name]['arch'] not in ('all', TARGET_ARCH):
        crossgrade_targets.add(full_name)

# crossgrade all essential packages to be able to finish crossgrade after reboot
for package, info in package_info.items():
    if info['is_essential'] and info['arch'] not in ('all', TARGET_ARCH):
        crossgrade_targets.add(package)

if len(unaccounted_hooks) > 0:
    print('The following hooks in /usr/share/initramfs-tools/hooks are unaccounted for:')
    for hook in unaccounted_hooks:
        print(f'\t{hook}')
    print('Aborting crossgrade.')
else:
    print(f'{len(crossgrade_targets)} targets found.')
    print(crossgrade_targets)
    # crossgrade(crossgrade_targets)
