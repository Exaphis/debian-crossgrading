import subprocess

current_arch = subprocess.check_output(['dpkg', '--print-architecture']).strip()
target_arch = b'arm64'

packages = subprocess.check_output(['dpkg-query', '-f', '${Package}\t${Architecture}\t${Status}\n', '-W']).splitlines()

crossgrade_targets = []
for package in packages:
    name, arch, status = package.split(b'\t')
    if status == b'install ok installed' and arch != target_arch:
        # must specify arch for packages installed in multiple architectures
        files = subprocess.check_output(['dpkg-query', '-L', name + b':' + arch]).splitlines()
        if any(f.startswith(b'/usr/share/initramfs-tools/hooks') for f in files):
            print(name)

