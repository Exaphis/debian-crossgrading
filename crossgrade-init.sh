#!/bin/sh

[ -d /dev ] || mkdir -m 0755 /dev
[ -d /root ] || mkdir -m 0700 /root
[ -d /sys ] || mkdir /sys
[ -d /proc ] || mkdir /proc
[ -d /tmp ] || mkdir /tmp
mkdir -p /var/lock
mount -t sysfs -o nodev,noexec,nosuid sysfs /sys
mount -t proc -o nodev,noexec,nosuid proc /proc

if [ "$quiet" != "y" ]; then
  quiet=n
  echo "Prepping qemu-user-static, please wait..."
fi

[ "$quiet" != "y" ] && echo "Loading binfmt_misc"
modprobe binfmt_misc
[ "$quiet" != "y" ] && echo "binfmt_misc loaded"

export DPKG_MAINTSCRIPT_ARCH="aarch64"
export DPKG_MAINTSCRIPT_NAME="postinst"
/postinsts/qemu-user-static-postinst configure
