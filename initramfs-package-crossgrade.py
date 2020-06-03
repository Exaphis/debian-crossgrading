import subprocess
import sys

current_arch = subprocess.check_output(['dpkg', '--print-architecture']).strip()
target_arch = b'arm64'

packages = subprocess.check_output(['dpkg-query', '-f', '${Package}\t${Architecture}\t${Status}\n', '-W']).splitlines()

crossgrade_targets = []
for package in packages:
    name, arch, status = package.split(b'\t')
    if status == b'install ok installed' and arch != target_arch and arch != b'all':
        # must specify arch for packages installed in multiple architectures
        full_name = name + b':' + arch
        files = subprocess.check_output(['dpkg-query', '-L', full_name]).splitlines()
        if any(f.startswith(b'/usr/share/initramfs-tools/hooks') for f in files):
            crossgrade_targets.append(name + b':' + target_arch)

print(f'{len(crossgrade_targets)} targets found.')
print(crossgrade_targets)
subprocess.check_call(['apt-get', 'install', crossgrade_targets, '-y'], stdout=sys.stdout, stderr=sys.stderr)

