# begin arch-check-hook

# All instances of TARGET_ARCH_PLACEHOLDER will be replaced by
# the real target architecture when the hook is installed.

# The line "# begin arch-check-hook" is used to check if the hook
# has been installed.

# $1 - file to check
# $2 - architecture to check file against
check_file_arch () {
    local file_arch detect_status
    file_arch=`elf-arch "${1}"`
    detect_status="${?}"

    elf-arch -a "${2}" "${1}"

    # detect_status being 0 means $1 contains a binary
    # must be used because elf-arch -a has exit code 1 for both file not being a binary
    # and file not being the right architecture
    if [ ${detect_status} -eq 0 -a $? -ne 0 ]; then
        echo "WARNING: initramfs binary ${1} has non-target architecture ${file_arch}."
        echo "Ensure that it can be executed or crossgrade the package, then update the initramfs again."
    fi
}

if command -v elf-arch > /dev/null; then
    check_file_arch ${1} "TARGET_ARCH_PLACEHOLDER"
else
    echo "arch-test is not installed. Install it for the binary arch test to function."
fi
# end arch-check-hook
