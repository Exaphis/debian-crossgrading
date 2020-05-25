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

copy_package() {
  local package="${1}"
  local initramfs_dir="${2}"
  local unzip_dir=$(mktemp -d)

  cd "${download_dir}"

  echo "Downloading ${package}..."
  apt-get download "${package}:${target_arch}"

  echo "Extracting ${package}..."
  dpkg -x ${package}* "${unzip_dir}"

  echo "Copying executable files to initramfs..."

  cd "${unzip_dir}"

  if [ "${initramfs_dir}" = "." ]; then
    find . -executable -type f -exec sh -c '. /usr/share/initramfs-tools/hook-functions; dest=${1#./}; copy_exec "${1}" "${dest}"; echo "Copied ${1} to /${dest}."' _ {} \;
  else
    find . -executable -type f -exec sh -c '. /usr/share/initramfs-tools/hook-functions; dest=${1#./}; copy_exec "${1}" "${2}/${dest}"; echo "Copied ${1} to /${2}/${dest}."' _ {} ${initramfs_dir} \;
  fi

  echo "Copying postinst script..."
  rm -r ./*
  cd "${download_dir}"
  dpkg -e ${package}* "${unzip_dir}"

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
}

set -e

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

target_arch="amd64"
copy_package busybox-static busybox-amd64

rm -r "${download_dir}"
