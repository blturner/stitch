import collections
import os

from fabric.api import env
from fabric.api import local as _local
from fabric.api import run as _run
from fabric.context_managers import cd as _cd
from fabric.context_managers import lcd as _lcd
from fabric.contrib.files import exists as _exists
from fabric.operations import put as _put
from fabric.operations import sudo as _sudo


def update(d, u):
    """
    Utility function that takes a dictionary and updates keys with values from
    a second dictionary. http://stackoverflow.com/a/3233356
    """
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def cd(path):
    if _is_local(env.host):
        return _lcd(path)
    else:
        return _cd(path)


def run(command, capture=False, shell=True, pty=True):
    if _is_local(env.host):
        return _local(command % (env), capture=capture)
    else:
        return _run(command % (env), shell=shell, pty=pty)


def exists(path):
    if _is_local(env.host):
        return os.path.exists(os.path.expanduser(path))
    else:
        return _exists(path)


def put(output, target):
    if _is_local(env.host):
        f = open(target, 'w')
        f.write(output.getvalue())
        f.close()
    else:
        _put(output, target)


def restart():
    if _is_local(env.host):
        _local('sudo apachectl graceful')
    else:
        _sudo('apache2ctl graceful')


def _is_local(host):
    if host in env.roledefs['local']:
        return True
    return False
