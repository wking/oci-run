#!/usr/bin/env python3
#
# Copyright (C) 2016 W. Trevor King <wking@tremily.us>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json as _json
import logging as _logging
import os as _os
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import uuid as _uuid

import prctl as _prctl


_LOG = _logging.getLogger(__name__)
_LOG.addHandler(_logging.StreamHandler())
_LOG.setLevel(_logging.ERROR)
_SIGNALS = {
    _signal.SIGCHLD: 'SIGCHLD',
}
_EXPECTED_PIDS = []
_REAPED_CHILDREN = {}


class HookError(RuntimeError):
    def __init__(self, hook, status):
        self.hook = hook
        self.status = status
        message = 'hook {} exited with status {}'.format(hook, status)
        super(HookError, self).__init__(message)


def _reap(signal, frame):
    name = _SIGNALS.get(signal, signal)
    pid, status = _os.wait()
    _REAPED_CHILDREN[pid] = status


def _get_hooks(path='hooks.json', keys=None):
    try:
        with open(path, 'rb') as f:
            hook_bytes = f.read()
    except FileNotFoundError:
        hooks = {}
    else:
        hooks = _json.loads(hook_bytes.decode('UTF-8'))
        if keys:
            for key in keys:
                hooks = hooks.get(key, {})
    for event in ['prestart', 'poststart', 'poststop']:
        for hook in hooks.get(event, []):
            if 'timeout' in hook:
                raise NotImplementedError('hook.timeout is not supported yet')
    return hooks


def _run(name, **kwargs):
    if isinstance(kwargs.get('stdin'), bytes):
        if 'stdout' in kwargs or 'stderr' in kwargs:
            raise NotImplementedError(
                'cannot write bytes to stdin if stdout or stderr are specified'
            )
        stdin = kwargs['stdin']
        kwargs['stdin'] = _subprocess.PIPE
    else:
        stdin = None
    process = _subprocess.Popen(**kwargs)
    _LOG.debug('spawned {} process with PID {}'.format(name, process.pid))
    if stdin:
        try:
            # stdin is buffered in the kernel, so this won't block for
            # sufficiently small state
            process.stdin.write(stdin)
            process.stdin.flush()
            process.stdin.close()
        except BrokenPipeError:
            pass
    while process.pid not in _REAPED_CHILDREN:
        _signal.pause()
    status = _REAPED_CHILDREN[process.pid]
    _LOG.debug('{} process exited with {}'.format(name, status))
    return status


def _run_hook(name, hook, state_bytes, strict=True):
    status = _run(
        name=name,
        args=hook['args'],
        executable=hook.get('path'),
        env=hook.get('env'),
        stdin=state_bytes,
    )
    if status != 0 and strict:
        raise HookError(hook=hook, status=status)


def _delete(runtime, container_id):
    _run(name='delete', args=runtime + ['delete', container_id])


def main(runtime=['runc'], container_id=None):
    if container_id is None:
        container_id = _uuid.uuid4().hex

    _signal.signal(_signal.SIGCHLD, _reap)
    _prctl.set_child_subreaper(1)

    hooks = _get_hooks(path='hooks.json')

    status = _run(name='create', args=runtime + ['create', container_id])
    if status != 0:
        _sys.exit(1)

    state_process = _subprocess.Popen(
        args=runtime + ['state', container_id],
        stdin=_subprocess.PIPE,
        stdout=_subprocess.PIPE,
        stderr=_subprocess.PIPE,
    )
    _LOG.debug('spawned state process with PID {}'.format(state_process.pid))
    state_bytes, stderr = state_process.communicate()
    while state_process.pid not in _REAPED_CHILDREN:
        _signal.pause()
    status = _REAPED_CHILDREN[state_process.pid]
    _LOG.debug('state process exited with {}'.format(status))
    if status != 0:
        _LOG.error(stderr.strip())
        _delete(runtime=runtime, container_id=container_id)
        _sys.exit(1)

    state = _json.loads(state_bytes.decode('UTF-8'))
    container_pid = state['pid']

    for i, hook in enumerate(hooks.get('prestart', [])):
        _LOG.info('run pre-start hook {}'.format(i))
        try:
            _run_hook(hook=hook, state_bytes=state_bytes)
        except HookError as error:
            status = error.status
            _delete(runtime=runtime, container_id=container_id)
            _sys.exit(1)

    status = _run(name='start', args=runtime + ['start', container_id])
    if status != 0:
        _delete(runtime=runtime, container_id=container_id)
        _sys.exit(1)

    for i, hook in enumerate(hooks.get('poststart', [])):
        _LOG.info('run post-start hook {}'.format(i))
        _run_hook(hook=hook, state_bytes=state_bytes, strict=False)

    _LOG.debug('waiting on container process {}'.format(container_pid))
    while container_pid not in _REAPED_CHILDREN:
        _signal.pause()
    status = _REAPED_CHILDREN[container_pid]
    _LOG.debug('container process exited with {}'.format(status))

    for i, hook in enumerate(hooks.get('poststop', [])):
        _LOG.info('run post-stop hook {}'.format(i))
        _run_hook(hook=hook, state_bytes=state_bytes, strict=False)

    _delete(runtime=runtime, container_id=container_id)
    if status > 127:
        status = 127
    _sys.exit(status)


if __name__ == '__main__':
    _LOG.setLevel(_logging.DEBUG)
    main()
