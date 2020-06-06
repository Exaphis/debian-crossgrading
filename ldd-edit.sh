#!/bin/sh

set -e

# add dynamic linker for amd64 to ldd
# to detect shared libraries
ldd_bak_dir=$(mktemp -d)
cp /bin/ldd "${ldd_bak_dir}/ldd.bak"
sed -i '/^RTLDLIST=.*/a RTLDLIST="${RTLDLIST} /lib64/ld-linux-x86-64.so.2"' /bin/ldd
