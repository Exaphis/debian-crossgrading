# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/projects/#6528590289567744.

## Progress

- [x] Crossgrading initramfs packages
    - [ ] Reliable initramfs verification hook
- [ ] Rebooting into a non-broken state
    - [ ] ~~Use gdebi to install packages~~
    - [ ] ~~Install packages w/ topological sort instead of gdebi~~
    - [x] Install packages using looping `dpkg -i` and `dpkg --configure -a`
        - Source: https://anarc.at/services/upgrades/cross-architecture/
    - [ ] Fix systemd entering emergency mode
- [ ] Crossgrading remaining packages in target architecture

## Notes
* Crossgrading over ssh - make sure the ssh service does not break/go down
* Initramfs binary verification - how get architecture name in `file` reliably?
    * e.g. amd64 -> x86-64, arm64 -> ARM aarch64
    * Possible solution: download set package (hello?) using dpkg, and get the output of `file`

