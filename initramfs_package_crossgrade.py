from glob import glob
import subprocess
import sys


def crossgrade_packages(targets):
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


TARGET_ARCH = 'arm64'

packages = subprocess.check_output(['dpkg-query',
                                    '-f',
                                    '${Package}\t${Architecture}\t${Status}\n',
                                    '-W'], encoding='UTF-8').splitlines()

unaccounted_hooks = set(glob('/usr/share/initramfs-tools/hooks/*'))
crossgrade_targets = []
for package in packages:
    name, arch, status = package.split('\t')
    if status == 'install ok installed' and arch != TARGET_ARCH:
        # must specify arch for packages installed in multiple architectures
        full_name = f'{name}:{arch}'
        files = subprocess.check_output(['dpkg-query', '-L', full_name],
                                        encoding='UTF-8').splitlines()

        num_hooks = len(unaccounted_hooks)
        unaccounted_hooks.difference_update(files)

        if arch != 'all' and len(unaccounted_hooks) < num_hooks:
            crossgrade_targets.append(f'{name}:{TARGET_ARCH}')

if len(unaccounted_hooks) > 0:
    print('The following hooks in /usr/share/initramfs-tools/hooks are unaccounted for:')
    for hook in unaccounted_hooks:
        print(f'\t{hook}')
    print('Aborting crossgrade.')
else:
    print(f'{len(crossgrade_targets)} targets found.')
    print(crossgrade_targets)
