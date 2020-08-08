"""ELF file utilities used by debian_crossgrader."""
import struct


def e_machine(filename):
    """Returns a 2-byte bytestring of the ELF file's e_machine entry, or None if not an ELF.

    This function is to be used by arch-check-hook.sh to check if a given ELF is in the right
    architecture after crossgrading.
    """
    # pylint: disable=broad-except
    try:
        with open(filename, 'rb') as elf:
            if not elf.read(4) == b'\x7fELF':
                return None

            elf.seek(18)
            return struct.unpack('H', elf.read(2))[0]
    except Exception as exc:
        print(exc)
        return None


if __name__ == '__main__':
    print(e_machine('/usr/bin/dpkg'))
