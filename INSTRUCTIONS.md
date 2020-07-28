Notes before crossgrading
---

#### Backup the system

Crossgrading a Debian install is currently experimental and prone to breakages. Please, please, **please** back up your data before continuing!

#### Saving a list of currently installed packages

```
$ python3 crossgrade/utils/package_check/package_check.py
Saving currently installed packages...
Packages saved.
```

After crossgrading, run `python3 crossgrade/util/package_check/package_check.py` to verify that all packages were actually crossgraded.

#### Crossgrading over SSH

Crossgrading over SSH is possible, but not advised as internet connectivity might drop during the first stage of the crossgrading process.

If you are going to do it, use a terminal multiplexer such as `tmux` or `screen` so the crossgrading tool can continue to run even if the network connection drops.

Converting an i386 system to amd64
---

#### Setting up the crossgrade script

```
# apt install git dpkg-dev arch-test
# git clone https://salsa.debian.org/crossgrading-team/debian-crossgrading.git ~/debian-crossgrading
```

#### Adding the new architecture

```
# dpkg --add-architecture amd64
# apt update
```

#### Install the amd64 kernel

```
# apt install linux-image-amd64:amd64
# reboot
```

```
# uname -a
Linux buster-i386-amd64 4.19.0-9-amd64 #1 SMP Debian 4.19.118-2+deb10u1 (2020-06-07) x86_64 GNU/Linux
```

#### First stage -- initramfs, required, important

At this point, __switch to a text mode console__.

Crossgrade all Priority: required and Priority: important packages, as well as any packages containing initramfs hook scripts. This makes sure our core packages can be switched over to the target architecture.

```
# cd ~/debian-crossgrading
# python3 crossgrade.py amd64
```

#### Second stage -- the rest of the owl

Crossgrade all packages not in the target architecture (amd64).

```
# python3 crossgrade.py amd64 --second-stage
```

If a `PackageNotFoundError` is raised, use `--dry-run` with `--force-unavailable` to list all packages that cannot be crossgraded.

Most likely, some packages (e.g. `linux-image-686-pae`) will not have amd64 versions. If the packages do not need to be crossgraded, remove the packages manually and re-run the command. Alternatively, use the `--force-unavailable` flag to perform the crossgrade anyway.

After the second stage is complete, apt and dpkg should no longer complain about any broken/unconfigured packages. If any still remain, fix them manually.

#### Third stage -- cleanup

Remove all packages now deemed unnecessary by apt.

```
# apt autoremove
```

Remove all packages in the given architecture (i386).

```
# python3 crossgrade.py amd64 --third-stage i386
```

No packages should exist in the i386 architecture anymore, so it can be removed as a foreign dpkg architecture.

```
# dpkg --remove-architecture i386
```

The crossgrade is complete!

Asciicasts
---

A sample crossgrade from i386 to amd64 of a Debian Buster image can be viewed below.

The process is separated by system reboots into three asciicasts.

[![asciicast](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl.png)](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl)

[![asciicast2](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8.png)](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8)

[![asciicast3](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs.png)](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs)

Converting an arm64 system to amd64
---

```
# apt update
# apt upgrade
# apt install qemu-user-static git dpkg-dev arch-test
# dpkg --add-architecture amd64
# apt update
# apt install linux-image-amd64:amd64 grub-efi:amd64
# git clone https://salsa.debian.org/crossgrading-team/debian-crossgrading.git
# cd debian-crossgrading
# python3 crossgrade/crossgrade.py amd64
# update-initramfs -u -k all  # might take a long time
# reboot
```

After booting the install with an amd64 system, fix any internet connectivity issues before continuing.

In my case, I had to change the primary network interface to ens3.

If needed, running --second-stage will crossgrade qemu-user-static and its dependencies so the system can run arm64 binaries.

Before qemu-user-static is crossgraded, sudo might take a long time to execute. Logging in as root to perform the crossgrade will work around the issue.

```
# cd debian-crossgrading
# python3 crossgrade/crossgrade.py amd64 --second-stage
# python3 crossgrade/crossgrade.py amd64 --third-stage arm64
# dpkg --remove-architecture arm64
```
