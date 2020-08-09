# begin arch-check-hook

# The line "# begin arch-check-hook" is used to check if the hook
# has been installed.

# $1 - file to check
# $2 - architecture to check file against
check_file_arch () {
    local arch_match arch_match_output
    arch_match_output=$(python3 -c "import sys; from debian_crossgrader.utils.elf import e_machine; val=e_machine('${1}'); sys.exit(0 if val is None else val != e_machine('/usr/bin/dpkg'))")
    arch_match=${?}

    # do not print trailing newline to prevent unnecessary prepending
    printf '%s' "${arch_match_output}" | sed 's/^/crossgrader initramfs hook: /'

    if [ ${arch_match} -ne 0 ]; then
        echo "crossgrader initramfs hook: (WARNING) initramfs binary ${1} might not be in the correct architecture."
        echo 'crossgrader initramfs hook: Ensure that it can be executed or crossgrade the package containing it, then update the initramfs again.'
        echo "crossgrader initramfs hook: output of \`file ${1}\`:"
        file "${1}"
    fi
}

check_file_arch "${1}"
# end arch-check-hook
