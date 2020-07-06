# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/projects/#6528590289567744.

## Usage

Refer to [INSTRUCTIONS.md](INSTRUCTIONS.md)

## Progress

### To-do

- [ ] Rewrite code for Python 3.4 support (to support Jessie)
    - [ ] Replacing f-strings with `''.format()`
    - [ ] Replacing `text=True` with `universal_newlines=True`
    - [ ] Replacing `subprocess.run()` calls
- [ ] Check that arm64 -> amd64 still works
- [ ] Initramfs binary arch checking

### arm64 -> amd64 crossgrade

- [x] Crossgrading initramfs packages
    - [ ] Reliable initramfs verification hook
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


## Notes for future me...
* Crossgrading over ssh - make sure the ssh service does not break/go down
* Initramfs binary verification - how get architecture name outputted by `file` reliably?
    * e.g. amd64 (dpkg) -> x86-64 (file), arm64 -> ARM aarch64
    * Solution: get output of `file /bin/dpkg`
* Should we make sure the size of the new initramfs will not exceed the total amount of RAM available?
* How can we point the bootloader to the right kernel/initramfs without user input?
* Automate initial crossgrade of qemu-user-static/binfmt-support after reboot to target arch
