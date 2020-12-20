# crossgrader TODO

## Incomplete

### Testing

- [ ] Testing with different init system

- [ ] Investigate why packages like transmission-gtk are being autoremoved
  after i386 to amd64

- [ ] Investigate why initramfs build is failing with plymouth
  (libpango-1.0.so is missing) and find how to fix

- [ ] Testing on non-usrmerge systems

- [ ] Testing with non-amd64 target (i.e. mipsel to mips64el, amd64 to arm64)

- [ ] Are there initial ramdisk hooks outside of `/usr/share/initramfs-tools/hooks`?
  `/etc/initramfs-tools/hooks`?

- [ ] Testing with /home, /var, /tmp on different partitions

### Functionality

- [ ] Log everything during crossgrade

- [ ] Maintain package hold status

- [ ] Configurable crossgrader-package-check output location

- [ ] Output summary to stdout in crossgrader-package-check

### Misc

- [ ] Show asciicasts more prominently (in crossgrader-doc package?)

- [ ] Update <https://wiki.debian.org/CrossGrading>

## Completed

### arm64 -> amd64 crossgrade

- [x] Rebooting into a non-broken state
  - [ ] ~~Use gdebi to install packages~~
  - [ ] ~~Install packages w/ topological sort instead of gdebi~~
  - [x] Install packages using looping `dpkg -i` and `dpkg --configure -a`
    - Source: <https://anarc.at/services/upgrades/cross-architecture/>
  - [x] Fix systemd entering emergency mode
    - Fixed by crossgrading all Priority: required packages
  - [x] Download packages using python-apt instead
    of apt-get --download-only install
    - Prevents download from failing when apt can't resolve dependencies
    - Now it can download install all Priority: required/important packages

- [x] Crossgrading remaining packages in target architecture
  - [x] Fix internet access in amd64 (crossgrade ifupdown)
    - Add new network interface to /etc/network/interfaces
  - [x] Crossgrade other essential packages after reboot
    - [x] Pre-download qemu-user-static and its dependencies
      - Crossgrade binfmt-support
        - Otherwise, it tries to run amd64 binaries w/
        qemu-user-x86_64, causing "Too many levels of symbolic links"
      - Uninstall qemu-user-static:arm64
      - Install qemu-user-static:amd64
    - [x] Pre-download python3 and its dependencies
    - [x] Be able to to manually specify packages to crossgrade in script
    - [x] Second-stage functionality - crossgrading remaining packages

### Misc

- [x] Initramfs binary arch verification
  - ~~How to get architecture name outputted by `file` reliably?~~
    - ~~E.g. amd64 (dpkg) -> x86-64 (file), arm64 -> ARM aarch64~~
    - ~~Solution: get output of `file /bin/dpkg`~~
  - ~~Use arch-test's elf-arch to get the architecture of copied binaries and
    check if it matches the target architecture~~ (arch-test's elf-arch not
    available in stretch)
  - Check ELF e_machine entry

- [x] Document crossgrade between architectures not supported on the same CPU
  - Still can be improved

- [x] Fixing all packages being marked as manually installed after crossgrade
  - [x] Testing...

- [x] Testing with non-64-bit target (i.e. amd64 to i386)

- [x] Automate initial crossgrade of qemu-user-static/binfmt-support
  after reboot to target arch

- [x] Testing on Stretch

- [x] Stop using elf-arch in initramfs hook (arch-test doesn't have it in Stretch)

- [x] Crossgrade current shell

- [x] Automatically crossgrade dependencies of crossgrader instead of
  explicitly crossgrading python3 and python-apt

- [x] Crossgrade dpkg/apt first before downloading

- [x] Install README.md and INSTRUCTIONS.md to /usr/share/doc/crossgrader

- [x] Bug#976433 - include Vcs fields in debian/control

### Packaging

- [x] Packaging crossgrade tool
  - [x] Python packaging
  - [x] Debian packaging

- [x] Add qemu-user-static to depends

- [x] Close ITP bug (966533)

- [x] Create manpage for binaries

### Supporting Debian Jessie

- [x] Rewrite code for Python 3.4 support
  - Replace f-strings with `''.format()`
  - Replace `text=True` with `universal_newlines=True`
  - Replace `subprocess.run()` calls
  - [x] Main crossgrade script
  - [x] Util scripts

## Notes

- Should we make sure the size of the new initramfs will not exceed the total
  amount of RAM available?

- How can we point the bootloader to the right kernel/initramfs without user input?
