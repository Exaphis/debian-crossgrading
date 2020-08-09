"""Functions for listing user shells"""
# Taken from arthurdejong's nss-pam-ldapd (LGPL v2.1+)
# https://github.com/arthurdejong/nss-pam-ldapd/blob/b33551895b3c02dc7082363c6aae13f8e336f4e5/utils/shells.py

import ctypes
import ctypes.util

def list_shells():
    """Return a list of valid user shell paths"""
    libc = ctypes.CDLL(ctypes.util.find_library('c'))

    getusershell = libc.getusershell
    getusershell.restype = ctypes.c_char_p

    libc.setusershell()

    out = []
    while True:
        shell = getusershell()
        if shell is None:
            break
        out.append(shell.decode('utf-8'))

    libc.endusershell()

    return out
