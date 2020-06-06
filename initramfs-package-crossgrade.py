from glob import glob
import subprocess
import sys

current_arch = subprocess.check_output(['dpkg', '--print-architecture'], encoding='UTF-8').strip()
target_arch = 'arm64'

packages = subprocess.check_output(['dpkg-query', '-f', '${Package}\t${Architecture}\t${Status}\n', '-W'], encoding='UTF-8').splitlines()

unaccounted_hooks = set(glob('/usr/share/initramfs-tools/hooks/*'))
crossgrade_targets = []
for package in packages:
    name, arch, status = package.split('\t')
    if status == 'install ok installed' and arch != target_arch:
        # must specify arch for packages installed in multiple architectures
        full_name = f'{name}:{arch}'
        files = subprocess.check_output(['dpkg-query', '-L', full_name], encoding='UTF-8').splitlines()

        num_hooks = len(unaccounted_hooks)
        unaccounted_hooks.difference_update(files)

        if arch != 'all' and len(unaccounted_hooks) < num_hooks:
            crossgrade_targets.append(f'{name}:{target_arch}')

if len(unaccounted_hooks) > 0:
    print('The following hooks in /usr/share/initramfs-tools/hooks are unaccounted for:')
    for hook in unaccounted_hooks:
        print(f'\t{hook}')
    print('Aborting crossgrade.')
else:
    print(f'{len(crossgrade_targets)} targets found.')
    print(crossgrade_targets)

    # clean apt-get cache
    subprocess.check_call(['apt-get', 'clean'])

    # call apt to cache .deb for package and dependencies
    # crossgrade in one command to prevent repeat triggers (e.g. initramfs rebuild), which saves time
    # dpkg performs the crossgrade (why? https://lists.debian.org/debian-devel-announce/2012/03/msg00005.html, unsure if this is up-to-date)
    # use the --force-depends option to avoid having to topologically sort the packages to see which to install first based on dependencies
    subprocess.check_call(['apt-get', '--download-only', 'install', *crossgrade_targets, '-y'], stdout=sys.stdout, stderr=sys.stderr)
    subprocess.check_call(['dpkg', '-i', '--force-depends', '/var/cache/apt/archives/*.deb'], stdout=sys.stdout, stderr=sys.stderr)

