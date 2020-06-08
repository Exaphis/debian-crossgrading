# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/projects/#6528590289567744.

## Progress

- [x] Crossgrading initramfs packages
- [ ] Rebooting into a non-broken state
    - [x] Use gdebi to install packages
    - [ ] Install packages w/ topological sort instead of gdebi
- [ ] Crossgrading final packages

## Notes
* Crossgrading over ssh - make sure the ssh service does not break/go down
