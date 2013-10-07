import tempfile
import shutil
import os

from fabric.api import *

env.use_ssh_config = True
env.hosts = ['s1.survey.tx.ai', 's2.survey.tx.ai', 's3.survey.tx.ai']

DEBS = ['ntp',
        'collectd',
        'emacs23-nox',
        'curl',
        'nginx',
        'libhiredis*',
        ]

@task
def install_debs():
    "Install and upgrade debian dependencies."
    sudo('apt-get update')
    sudo('apt-get dist-upgrade -y')
    sudo('apt-get install -y ' + ' '.join(DEBS))
    sudo('apt-get autoremove -y')

@task
def set_timezone():
    "Set timezone to Etc/UTC."
    sudo('echo "Etc/UTC" > /etc/timezone')
    sudo('dpkg-reconfigure -f noninteractive tzdata')

@task
def install_pip():
    "Install latest setuptools and pip from upstream."
    sudo('wget https://bitbucket.org/pypa/setuptools/raw/bootstrap/'
         'ez_setup.py -O - | python')
    run('rm setuptools-*.tar.gz')
    sudo('wget https://raw.github.com/pypa/pip/master/contrib/'
         'get-pip.py -O - | python')

@task
def install_tasa():
    "Install tasa."
    sudo('pip install -U tasa')

@task
def configure_collectd():
    "Configure collectd"
    put('configs/collectd.conf', '/etc/collectd/collectd.conf', use_sudo=True)
    sudo('service collectd restart')

@task
def configure_nginx():
    "Configure nginx"
    sudo('rm /etc/nginx/sites-enabled/*')
    put('configs/redir_to_main.nginx',
        '/etc/nginx/sites-enabled/redir_to_main',
        use_sudo=True)
    sudo('service nginx restart')

@task
@runs_once
def compile_masscan():
    "Download and compile latest masscan"
    try:
        os.remove('masscan')
    except OSError:
        pass
    local('sudo apt-get install -y build-essential libpcap-dev')
    tempdir = tempfile.mkdtemp()
    with lcd(tempdir):
        local('git clone https://github.com/robertdavidgraham/masscan')
        with lcd('masscan'):
            local('make')
            local('make regress')
    shutil.move(os.path.join(tempdir, 'masscan/bin/masscan'),
                '.')
    shutil.rmtree(tempdir)

@task
def configure_masscan():
    "Copy masscan configuration"
    sudo('mkdir -p /etc/masscan')
    put('configs/masscan.conf', '/etc/masscan/masscan.conf',
        use_sudo=True)
    put('configs/excludes.txt', '/etc/masscan/excludes.txt',
        use_sudo=True)

@task
def copy_masscan():
    "Copy the masscan binary to remote"
    put('masscan', '/usr/local/bin/masscan',
        use_sudo=True, mirror_local_mode=True)

@task
def install_masscan():
    "Take all steps to compile and install masscan remotely"
    compile_masscan()
    copy_masscan()
    configure_masscan()

@task
def reboot():
    "Reboot all machines. Doesn't wait."
    sudo('reboot now')

@task
def configure_survey():
    "Run all configuration steps to set up a survey slave"
    install_debs()
    set_timezone()
    install_pip()
    install_tasa()
    configure_collectd()
    configure_nginx()

    install_masscan()

    reboot()
