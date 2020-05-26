#!/bash-amd64/bin/sh

[ -d /dev ] || /coreutils-amd64/bin/mkdir -m 0755 /dev
[ -d /root ] || /coreutils-amd64/bin/mkdir -m 0700 /root
[ -d /sys ] || /coreutils-amd64/bin/mkdir /sys
[ -d /proc ] || /coreutils-amd64/bin/mkdir /proc
[ -d /tmp ] || /coreutils-amd64/bin/mkdir /tmp
/coreutils-amd64/bin/mkdir -p /var/lock
/coreutils-amd64/bin/mount -t sysfs -o nodev,noexec,nosuid sysfs /sys
/coreutils-amd64/bin/mount -t proc -o nodev,noexec,nosuid proc /proc

if [ "$quiet" != "y" ]; then
  quiet=n
  /coreutils-amd64/bin/echo "Prepping qemu-user-static, please wait..."
fi

[ "$quiet" != "y" ] && /coreutils-amd64/bin/echo "Loading binfmt_misc"
/coreutils-amd64/bin/cd /kmod
/coreutils-amd64/bin/ln -s modprobe ./bin/kmod
./modprobe binfmt_misc
/coreutils-amd64/bin/cd /
[ "$quiet" != "y" ] && echo "binfmt_misc loaded"

export DPKG_MAINTSCRIPT_ARCH="amd64"
export DPKG_MAINTSCRIPT_NAME="postinst"
/coreutils-amd64/bin/mkdir -p /var/lib/binfmts
/postinsts/qemu-user-static-postinst configure
