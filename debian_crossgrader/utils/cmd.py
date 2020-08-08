"""Functions to make calling shell commands easier."""

import fcntl
import os
import sys
import select

def tee_process(process):
    """Outputs the process' stdout and stderr to stdout while recording it.

    Ideas and code from https://stackoverflow.com/a/7730201 and
    https://github.com/catapult-project/catapult/blob/master/devil/devil/utils/cmd_helper.py#L214.

    Args:
        process: subprocess.Popen object representing the process. Its stdout
            and stderr should be set to subprocess.PIPE.
    Returns:
        A tuple in the form of (exit_code, stdout, stderr).
    """

    def make_async(child_fd):
        """Add the O_NONBLOCK flag to a file description"""
        file_status = fcntl.fcntl(child_fd, fcntl.F_GETFL)
        fcntl.fcntl(child_fd, fcntl.F_SETFL, file_status | os.O_NONBLOCK)

    def write_contents(child_fds, output_dict, is_text):
        """Write contents of file descriptors to stdout and output_dict.

        Returns:
            True if any data was read, False otherwise.
        """
        data_read = False
        for child_fd in child_fds:
            data = child_fd.read()

            if data:
                data_read = True

                if is_text:
                    sys.stdout.write(data)
                else:
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()

                output_dict[child_fd.fileno()].append(data)

        return data_read


    try:
        text_mode = process.text_mode
    except AttributeError:  # workaround for Python 3.5
        text_mode = process.universal_newlines

    # stdout/stderr can be None if they are set to sys.stdout/sys.stderr
    process_outs = []
    if process.stdout is not None:
        make_async(process.stdout)
        process_outs.append(process.stdout)
    if process.stderr is not None:
        make_async(process.stderr)
        process_outs.append(process.stderr)

    output_bufs = {proc_fd.fileno(): [] for proc_fd in process_outs}

    while True:
        read_fds, __, __ = select.select(process_outs, [], [], 1)
        has_data = write_contents(read_fds, output_bufs, text_mode)

        if process.poll() is not None and not has_data:
            break

    stdout_data = output_bufs[process.stdout.fileno()] if process.stdout is not None else []
    stderr_data = output_bufs[process.stderr.fileno()] if process.stderr is not None else []

    if text_mode:
        separator = ''
    else:
        separator = b''

    return process.poll(), separator.join(stdout_data), separator.join(stderr_data)
