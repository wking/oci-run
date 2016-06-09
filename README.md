# OCI Run

A single-command wrapper around OCI's [create/start/delete][lifecycle]
for folks who liked the old
[single-command lifecycle and its hooks][lifecycle-0.5.0].

This package only works on Linux (because [prctl][prctl.2] is
Linux-specific).

## Dependencies

`run.py` requires [Python][] 3.4+ and the following packages:

* [python-prctl][] (GPLv3) for [prctl][prctl.2] bindings.

Install them with your package manager or:

```sh
$ pip3 install --user -r requirements.txt
```

## Bugs

The [`timeout` hook argument][timeout] is not supported yet.

[lifecycle]: https://github.com/opencontainers/runtime-spec/blob/v1.0.0-rc1/runtime.md#lifecycle
[lifecycle-0.5.0]: https://github.com/opencontainers/runtime-spec/blob/v0.5.0/runtime.md#lifecycle
[timeout]: https://github.com/opencontainers/runtime-spec/blob/v0.5.0/config.md#poststop

[Python]: https://www.python.org/
[python-prctl]: https://pypi.python.org/pypi/python-prctl

[prctl.2]: http://man7.org/linux/man-pages/man2/prctl.2.html
