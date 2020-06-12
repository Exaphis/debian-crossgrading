# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/projects/#6528590289567744.

## Progress

- [x] Crossgrading initramfs packages
    - [ ] Reliable initramfs verification hook
- [x] Rebooting into a non-broken state
    - [ ] ~~Use gdebi to install packages~~
    - [ ] ~~Install packages w/ topological sort instead of gdebi~~
    - [x] Install packages using looping `dpkg -i` and `dpkg --configure -a`
        - Source: https://anarc.at/services/upgrades/cross-architecture/
    - [x] Fix systemd entering emergency mode
        - Fixed by crossgrading all Priority: required packages
- [ ] Crossgrading remaining packages in target architecture
    - [ ] Fix internet access in amd64 (crossgrade ifupdown)
    - [ ] Download packages using python-apt instead of apt-get --download-only install
        - Prevents download from failing when apt can't resolve dependencies

## Notes
* Crossgrading over ssh - make sure the ssh service does not break/go down
* Initramfs binary verification - how get architecture name in `file` reliably?
    * e.g. amd64 -> x86-64, arm64 -> ARM aarch64
    * Possible solution: download set package (hello?) using dpkg, and get the output of `file`

