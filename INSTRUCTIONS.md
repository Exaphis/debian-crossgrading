Converting an i386 system to amd64
---

#### Backup the system

Crossgrading a Debian install is currently very experimental and prone to breakages. Please, please, **please** back up your data before continuing!

#### TODO: package saving

#### Setting up the crossgrade script

```
# apt install git dpk-dev
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

Most likely, some packages (e.g. `linux-image-686-pae`) will not have amd64 versions. If so, use the --force-unavailable flag to perform the crossgrade anyway.

TODO: dry run option

After this point, apt and dpkg should no longer complain about any broken/unconfigured packages. If any still remain, fix them manually.

#### Third stage -- cleanup

Removes all packages now deemed unnecessary by apt.

```
# apt autoremove
```

Removes all packages in the given architecture (i386).

```
# python3 crossgrade.py amd64 --third-stage i386
```

No packages should exist in the i386 architecture anymore, so it can be removed as a foreign dpkg architecture.

```
# dpkg --remove-architecture i386
```

Asciicasts
---

A sample crossgrade from i386 to amd64 of a Debian Buster image can be viewed below.

The process is separated by system reboots into three asciicasts.

[![asciicast](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl.png)](https://asciinema.org/a/e5zeJXw558vpMU8uolw20VVHl)

[![asciicast2](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8.png)](https://asciinema.org/a/bBYeBAlCii0qDpkog3XHTwIi8)

[![asciicast3](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs.png)](https://asciinema.org/a/GtdoAGtxsrAfHnyGiRu2QwPLs)
