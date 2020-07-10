# arch-check-hook
target_arch="ARCH_PLACEHOLDER"

file_arch=`elf-arch "$src"`
detect_status="$?"

elf-arch -a "$target_arch" "$src"

if [ detect_status -eq 0 -a $? -ne 0 ]
    echo "WARNING: initramfs binary $src has non-target architecture $file_arch."
    echo "Ensure that it can be executed or crossgrade the package, then update the initramfs again."
fi

