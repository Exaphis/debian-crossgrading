#!/bin/sh

# hook should be installed in /usr/share/initramfs-tools/hooks
PREREQ="zzbusybox"
prereqs()
{
  echo "$PREREQ"
}

case $1 in
prereqs)
  prereqs
  exit 0
  ;;
esac

. /usr/share/initramfs-tools/hook-functions

cleanup() {
  [ -z "${download_dir}" ] && rm -r "${download_dir}"
  [ -z "${unzip_dir}" ] && rm -r "${unzip_dir}"

  if [ -z "${ldd_bak_dir}" ]; then
    mv "${ldd_bak_dir}/ldd.bak" /bin/ldd
    rm -r "${ldd_bak_dir}"
  fi
}

trap cleanup EXIT

copy_package() {
  package="${1}"
  initramfs_dir="${2}"
  unzip_dir=$(mktemp -d)

  cd "${download_dir}"

  echo "Downloading ${package}..."
  apt-get download "${package}:${target_arch}"

  echo "Extracting ${package}..."
  dpkg -x "${package}"* "${unzip_dir}"

  echo "Copying executable files to initramfs..."

  cd "${unzip_dir}"

  if [ "${initramfs_dir}" = "." ]; then
    find . -executable -type f -exec sh -c '. /usr/share/initramfs-tools/hook-functions; dest=${1#./}; copy_exec "${1}" "${dest}"; echo "Copied ${1} to /${dest}."' _ {} \;
  else
    find . -executable -type f -exec sh -c '. /usr/share/initramfs-tools/hook-functions; dest=${1#./}; copy_exec "${1}" "${2}/${dest}"; echo "Copied ${1} to /${2}/${dest}."' _ {} "${initramfs_dir}" \;
  fi

  echo "Copying postinst script..."
  rm -r ./*
  cd "${download_dir}"
  dpkg -e "${package}"* "${unzip_dir}"
  rm "${package}"*

  if [ -f "${unzip_dir}/postinst" ]; then
    mv "${unzip_dir}/postinst" "${unzip_dir}/${package}-postinst"
    copy_exec "${unzip_dir}/${package}-postinst" postinsts
    echo "Postinst copied to /postinsts."
  else
    echo "Postinst does not exist."
  fi

  echo "${package} copied."
  echo ""
  rm -r "${unzip_dir}"
  unzip_dir=""
}

set -e

# add dynamic linker for amd64 to ldd
# to detect shared libraries
ldd_bak_dir=$(mktemp -d)
cp /bin/ldd "${ldd_bak_dir}/ldd.bak"
sed '/^RTLDLIST=.*/a RTLDLIST="${RTLDLIST} /lib64/ld-linux-x86-64.so.2"' /bin/ldd

# possibly needed for some deps?
apt-get install -y libc6:amd64

# mount
apt-get install -y libblkid1:amd64
apt-get install -y libmount1:amd64
apt-get install -y libselinux1:amd64
apt-get install -y libsmartcols1:amd64

# coreutils
apt-get install -y libacl1:amd64
apt-get install -y libattr1:amd64

# kmod
apt-get install -y libkmod2:amd64
apt-get install -y liblzma5:amd64
apt-get install -y libssl1.1:amd64

# used by qemu-user-static to run foreign arch binaries
force_load binfmt_misc

download_dir=$(mktemp -d)
chown _apt "${download_dir}"

# qemu-user-static's postinst uses nested parameter
# expansion, which is not supported in POSIX shells.
# so we need to use bash to run it
copy_exec /bin/bash /bin

target_arch="arm64"
copy_package binfmt-support .
copy_package qemu-user-static .
copy_package busybox-static busybox-arm64

target_arch="amd64"
copy_package busybox-static busybox-amd64
copy_package bash bash-amd64
copy_package mount mount-amd64
copy_package coreutils coreutils-amd64
copy_package kmod kmod-amd64

# change /bin/sh symlink to point to new bash
# so init script can be run in new arch
ln -sf /bash-amd64/bin/bash "${DESTDIR}/bin/sh"

wget -O "${DESTDIR}/crossgrade-init" "https://raw.githubusercontent.com/Exaphis/debian-crossgrading/master/crossgrade-init.sh"
chmod +x "${DESTDIR}/crossgrade-init"
