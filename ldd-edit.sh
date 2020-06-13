#!/bin/sh

set -e

# add dynamic linker for amd64 to ldd so mkinitramfs can
# detect and copy shared libraries for amd64 binaries

# might be unnecessary now that all Priority: required/important
# packages are being crossgraded

ldd_bak_dir=$(mktemp -d)
cp /bin/ldd "${ldd_bak_dir}/ldd.bak"
sed -i '/^RTLDLIST=.*/a RTLDLIST="${RTLDLIST} /lib64/ld-linux-x86-64.so.2"' /bin/ldd
