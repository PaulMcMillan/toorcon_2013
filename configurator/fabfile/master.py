"""
Code to configure the survey's redis coordinator.

"""

import tempfile
import shutil
import os

from fabric.api import *

@task
@runs_once  # do this once, locally
def compile_redis():
    "Compile redis locally"
    tempdir = tempfile.mkdtemp()
    try:
        os.remove('redis-server')
    except OSError:
        pass
    try:
        os.remove('redis-cli')
    except OSError:
        pass

    with lcd(tempdir):
        local('wget https://github.com/antirez/redis/archive/2.6.16.tar.gz '
              '-O -| tar xz --strip 1')
        local('make')
        #local('make test')  # takes a long time
    shutil.move(os.path.join(tempdir, 'src/redis-server'),
                '.')
    shutil.move(os.path.join(tempdir, 'src/redis-cli'),
                '.')
    shutil.rmtree(tempdir)

@task
def configure_redis():
    "Copy redis configuration and scripts"
    sudo('mkdir -p /etc/redis')
    put('configs/redis.upstart', '/etc/init/redis.conf',
        use_sudo=True)
    put('configs/redis.conf', '/etc/redis/redis.conf',
        use_sudo=True)
    put('configs/redis-local.conf', '/etc/redis/redis-local.conf',
        use_sudo=True)

@task
def copy_redis():
    "Copy local redis binary to remote"
    put('redis-server', '/usr/local/bin/redis-server',
        use_sudo=True, mirror_local_mode=True)
    put('redis-cli', '/usr/local/bin/redis-cli',
        use_sudo=True, mirror_local_mode=True)

@task
def install_redis():
    "Compile, then install redis remotely"
    compile_redis()
    configure_redis()
    copy_redis()
    sudo('service redis restart', warn_only=True)
