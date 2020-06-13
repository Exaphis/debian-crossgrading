# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/projects/#6528590289567744.

## Progress

### General crossgrade procedure

1. Verify system is ready to crossgrade
    - Check remaining storage
    - Check apt - no broken dependencies/etc.
    - Check for packages not available in target architecture
2. Add new architecture to dpkg and update apt cache
3. Prepping system for crossgrade
    - Installing bootloader in target architecture
    - Installing kernel for target architecture
4. Crossgrade essential packages
5. Final touches so reboot is successful
    - Update target architecture initramfs
    - Ensure bootloader boots with the right kernel and initramfs
6. Reboot to new architecture
7. Crossgrade qemu-user-static
8. Crossgrade remaining packages

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
- [ ] Crossgrading remaining packages in target architecture
    - [x] Fix internet access in amd64 (crossgrade ifupdown)
        - Weird... system boots without internet access, but fixes itself after some time
    - [ ] Crossgrade other essential packages after reboot
        - [ ] Pre-download qemu-user-static and its dependencies
            1. Crossgrade binfmt-support
                - Otherwise, it tries to run amd64 binaries w/ qemu-user-x86_64, causing "Too many levels of symbolic links"
            2. Uninstall qemu-user-static:arm64
            3. Install qemu-user-static:amd64
        - [ ] Pre-download python3 and its dependencies
    - [ ] Be able to to manually specify packages to crossgrade in script
    - [ ] Second-stage functionality - crossgrading remaining packages


## Notes for future me...
* Crossgrading over ssh - make sure the ssh service does not break/go down
* Initramfs binary verification - how get architecture name outputted by `file` reliably?
    * e.g. amd64 (dpkg) -> x86-64 (file), arm64 -> ARM aarch64
    * Solution: get output of `file /bin/dpkg`
* Should we make sure the size of the new initramfs will not exceed the total amount of RAM available?
* How can we point the bootloader to the right kernel/initramfs without user input?

