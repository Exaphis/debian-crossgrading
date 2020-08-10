ncomplete
---
#### Miscellaneous
- [ ] Testing with different init system
- [ ] Investigate why packages like transmission-gtk are being autoremoved after i386 to amd64
- [ ] Investigate why initramfs build is failing with plymouth (libpango-1.0.so is missing) and find how to fix
- [ ] Testing on non-usrmerge systems
- [ ] Testing with non-amd64 target (i.e. mipsel to mips64el, amd64 to arm64)
- [ ] Are there initial ramdisk hooks outside of `/usr/share/initramfs-tools/hooks`? `/etc/initramfs-tools/hooks`?
- [ ] Is qemu-user OK to use or will the libraries be too much?
- [ ] Testing with /home, /var, /tmp on different partitions

Completed
---
#### arm64 -> amd64 crossgrade
- [x] Rebooting into a non-broken state
    - [ ] ~~Use gdebi to install packages~~
    - [ ] ~~Install packages w/ topological sort instead of gdebi~~
    - [x] Install packages using looping `dpkg -i` and `dpkg --configure -a`
        - Source: https://anarc.at/services/upgrades/cross-architecture/
    - [x] Fix systemd entering emergency mode
        - Fixed by crossgrading all Priority: required packages
    - [x] Download packages using python-apt instead of apt-get --download-only install
        - Prevents download from failing when apt can't resolve dependencies
        - Now it can download install all Priority: required/important packages
- [x] Crossgrading remaining packages in target architecture
    - [x] Fix internet access in amd64 (crossgrade ifupdown)
        - Add new network interface to /etc/network/interfaces
    - [x] Crossgrade other essential packages after reboot
        - [x] Pre-download qemu-user-static and its dependencies
            1. Crossgrade binfmt-support
                - Otherwise, it tries to run amd64 binaries w/ qemu-user-x86_64, causing "Too many levels of symbolic links"
            2. Uninstall qemu-user-static:arm64
            3. Install qemu-user-static:amd64
        - [x] Pre-download python3 and its dependencies
    - [x] Be able to to manually specify packages to crossgrade in script
    - [x] Second-stage functionality - crossgrading remaining packages

#### Miscellaneous
- [x] Initramfs binary arch verification
    - ~~How to get architecture name outputted by `file` reliably?~~
        - ~~E.g. amd64 (dpkg) -> x86-64 (file), arm64 -> ARM aarch64~~
        - ~~Solution: get output of `file /bin/dpkg`~~
    - Use arch-test's elf-arch to get the architecture of copied binaries and check if it matches the target architecture
- [x] Document crossgrade between architectures not supported on the same CPU
    - Still can be improved
- [x] Fixing all packages being marked as manually installed after crossgrade
    - [x] Testing...
- [x] Testing with non-64-bit target (i.e. amd64 to i386)
- [x] Automate initial crossgrade of qemu-user-static/binfmt-support after reboot to target arch
- [x] Stop using elf-arch in initramfs hook (arch-test doesn't have it in Stretch)
- [x] Crossgrade current shell
- [x] Automatically crossgrade dependencies of crossgrader instead of explicitly crossgrading python3 and python-apt

#### Packaging
- [x] Packaging crossgrade tool
    - [x] Python packaging
    - [x] Debian packaging
- [x] Add qemu-user-static to depends
- [x] Close ITP bug (966533)


#### Supporting Debian Jessie
- [x] Rewrite code for Python 3.4 support
    - Replace f-strings with `''.format()`
    - Replace `text=True` with `universal_newlines=True`
    - Replace `subprocess.run()` calls
    - [x] Main crossgrade script
    - [x] Util scripts

Notes
---
- Should we make sure the size of the new initramfs will not exceed the total amount of RAM available?
- How can we point the bootloader to the right kernel/initramfs without user input?
