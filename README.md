# debian-crossgrading

This repo contains my work and research for my Google Summer of Code 2020 project, Architecture Cross-Grading Support in Debian.

The official project can be found at https://summerofcode.withgoogle.com/archive/2020/projects/5453452689276928/.

## crossgrader

This package provides a tool to crossgrade (i.e. change the architecture) of a Debian install.
It also provides a tool to check if all packages were successfully crossgraded.

The crossgrader automatically handles binaries required by the initramfs,
packages marked as automatically installed, and crossgrades to architectures
not natively supported on the current CPU.

## Usage

Refer to [INSTRUCTIONS.md](INSTRUCTIONS.md)

## Progress

Refer to [TODO.md](TODO.md)
