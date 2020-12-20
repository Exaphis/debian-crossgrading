# How do I use crossgrader?

## Crossgrading stages

The crossgrading process is split into three stages, each run by its own
command.

Replace `TARGET_ARCH` with the architecture that you are crossgrading to and
replace `FROM_ARCH` with the architecture you are crossgrading from.

1. First stage - `crossgrader TARGET_ARCH`
    - Crossgrades all packages containing initramfs hooks (currently, files in
      `/usr/share/initramfs-tools/hooks`) so the system can load properly
    - Crossgrades all packages with Priority: required or Priority: important
    - Crossgrades crossgrader dependencies
    - Crossgrades all login shells
2. Second stage - `crossgrader TARGET_ARCH --second-stage`
    - Crossgrades qemu-user-static first if it is installed
    - Crossgrades all packages that are not in the architecture `TARGET_ARCH`
3. Third stage - `crossgrader TARGET_ARCH --third-stage FROM_ARCH`
    - Removes all packages in the architecture `FROM_ARCH`

After the third stage, `FROM_ARCH` can be removed from dpkg to
complete the crossgrade.

## Notes before crossgrading

### Back up the system

Crossgrading a Debian install is currently experimental and prone to breakages.
Please, please, **please** back up your data before continuing!

### dpkg/APT error messages

The crossgrader will spit out many error messages from dpkg.
This is normal and can usually be safely ignored.

**DO NOT** use dpkg/APT manually while crossgrader is running; this may cause
breakages.

### Handling `ambiguous package name` error during package removal

`xxx: ambiguous package name xxx with more than one installed instance`
is caused by [#812228][1].

This error commonly occurs while crossgrading the packages `python3-pil` and
`python3-cairo`. crossgrader handles these situations by deleting the package's
prerm scripts and trying to remove the package again.

Another solution is to manually edit the prerm file and specify the architecture
of the package in the calls to `dpkg-query`.

### Saving a list of currently installed packages

```console
# crossgrade-package-check
Saving currently installed packages...
Packages saved.
```

After crossgrading, run `crossgrade-package-check` again to verify that all
packages were actually crossgraded.

### Crossgrading the bootloader

For crossgrades to non-natively supported architectures (e.g. arm64 to amd64),
you must crossgrade the bootloader in the first stage. This can be done by
installing the appropriate bootloader package in the target architecture after
installing the target architecture's kernel.

For example, if using `grub` and crossgrading from arm64 to amd64, you should
install `grub-pc:amd64` or `grub-efi-amd64` depending on if you are using
BIOS or UEFI firmware on the target amd64 machine.

## Special cases

### Crossgrading over SSH

Crossgrading over SSH is possible, but it is not advised as internet
connectivity might drop during the first stage of the crossgrading process.

If you are going to do it, use a terminal multiplexer such as `tmux` or `screen`
so the crossgrading tool can continue to run even if the network connection
drops.

### Target architecture runnable in current architecture, but not vice versa

An example of this situation would be crossgrading from amd64 to i386. i386
binaries are runnable under amd64, but amd64 binaries cannot be run under i386
(even with qemu, see bug #604712)

Since qemu-user-static cannot emulate the current arch under the original arch,
the best way is to run the first *and* second stages of the crossgrader in
the original architecture before rebooting to the target arch. In the amd64 to
i386 case, you would run `crossgrader i386` and `crossgrader i386
--second-stage` before rebooting to an i386 kernel.

## Common usage

### Converting an i386 system to amd64

#### Setting up the crossgrader

```console
# apt install ./crossgrader_0.0.2_all.deb
```

#### Adding the new architecture

```console
# dpkg --add-architecture amd64
# apt update
```

#### Install the amd64 kernel

```console
# apt install linux-image-amd64:amd64
# reboot
```

Ensure you boot to the correct kernel. In GRUB, the option to boot to the new
kernel will be located in Advanced options.

```console
# uname -a
Linux buster-i386-amd64 4.19.0-9-amd64 #1 SMP Debian 4.19.118-2+deb10u1 (2020-06-07) x86_64 GNU/Linux
```

#### First stage -- initramfs, required, important

At this point, __switch to a text mode console__.

Crossgrade all Priority: required and Priority: important packages, as well as
any packages containing initramfs hook scripts. This makes sure our core
packages can be switched over to the target architecture.

```console
# crossgrader amd64
```

#### Second stage -- the rest of the owl

Crossgrade all packages not in the target architecture (amd64).

```console
# crossgrader amd64 --second-stage
```

If a `PackageNotFoundError` is raised, use `--dry-run` with
`--force-unavailable` to list all packages that cannot be crossgraded.

Most likely, some packages (e.g. `linux-image-686-pae`) will not have amd64
versions. If the packages do not need to be crossgraded, remove the packages
manually and re-run the command. Alternatively, use the `--force-unavailable`
flag to perform the crossgrade anyway.

After the second stage is complete, apt and dpkg should no longer complain about
any broken/unconfigured packages. If any still remain, fix them manually.

#### Third stage -- cleanup

Remove all packages now deemed unnecessary by apt.

```console
# apt autoremove
```

Remove all packages in the old architecture (i386).

```console
# crossgrader amd64 --third-stage i386
```

No packages should exist in the i386 architecture anymore, so it can be removed
as a foreign dpkg architecture.

```console
# dpkg --remove-architecture i386
```

The crossgrade is complete!

### Converting an arm64 system to amd64

```console
# apt update
# apt upgrade
# dpkg -i crossgrader_0.0.2_all.deb
# apt -f install
# dpkg --add-architecture amd64
# apt update
# apt install linux-image-amd64:amd64 grub-efi:amd64
# crossgrader amd64
# update-initramfs -u -k all  # this might take a long time
# reboot
```

`update-initramfs` must be run after the first stage to update the amd64
initramfs. Otherwise, it will still contain arm64 binaries, preventing the
system from booting in amd64.

After booting the install with an amd64 system, fix any internet connectivity
issues before continuing.

In my case, I had to change the primary network interface to ens3.

If qemu-user-static is installed, running --second-stage will crossgrade
qemu-user-static and its dependencies so the system can run arm64 binaries.

Before qemu-user-static is crossgraded, sudo might take a long time to execute.
Logging in as root to perform the crossgrade will work around the issue.

```console
# crossgrader amd64 --second-stage
# crossgrader amd64 --third-stage arm64
# dpkg --remove-architecture arm64
```

## Asciicasts

A sample crossgrade from i386 to amd64 of a Debian Buster image can be viewed
below.

The process is separated by system reboots into three asciicasts.

[![asciicast](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl.png)](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl)

[![asciicast2](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8.png)](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8)

[![asciicast3](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs.png)](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs)

[1]: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=812228
