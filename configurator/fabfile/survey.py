import tempfile
import shutil
import os

from fabric.api import *

env.use_ssh_config = True
env.roledefs['survey'] = [
    's1.survey.tx.ai',
    's2.survey.tx.ai',
    's3.survey.tx.ai',
    's4.survey.tx.ai',
    's5.survey.tx.ai',
    's6.survey.tx.ai',
    's7.survey.tx.ai',
    's8.survey.tx.ai',
    ]

DEBS = ['emacs23-nox',
        'unattended-upgrades',
        'ntp',  # turns out to be more important than you'd think
        'collectd',
        'nginx',
        'libhiredis*',
        'ethtool',
        ]

@task
def install_debs():
    "Install and upgrade debian dependencies."
    sudo('apt-get update')
    sudo('apt-get dist-upgrade -y')
    sudo('apt-get install -y ' + ' '.join(DEBS))
    sudo('apt-get autoremove -y')

@task
def configure_upgrades():
    "Configure unattended upgrades"
    put('configs/50unattended-upgrades',
        '/etc/apt/apt.conf.d/50unattended-upgrades',
        use_sudo=True)
    put('configs/unattended-upgrades-10periodic',
        '/etc/apt/apt.conf.d/10periodic',
        use_sudo=True)

@task
def set_timezone():
    "Set timezone to Etc/UTC."
    sudo('echo "Etc/UTC" > /etc/timezone')
    sudo('dpkg-reconfigure -f noninteractive tzdata')

@task
def install_pip():
    "Install latest setuptools and pip."
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
def configure_tasa():
    "Configure tasa."
    sudo('mkdir -p /etc/tasa')
    put('configs/tasa.conf', '/etc/tasa/tasa.conf')

@task
def configure_collectd():
    "Configure collectd"
    put('configs/collectd.conf', '/etc/collectd/collectd.conf', use_sudo=True)
    sudo('service collectd restart')

@task
def configure_nginx():
    "Configure nginx"
    sudo('rm /etc/nginx/sites-enabled/*')
    put('configs/optout.nginx',
        '/etc/nginx/sites-enabled/optout',
        use_sudo=True)
    sudo('mkdir -p /usr/share/nginx/www')
    put('configs/optout.html',
        '/usr/share/nginx/www/index.html')
    sudo('service nginx restart')

@task
@runs_once  # do this once, locally
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
    "Compile masscan locally and install remotely"
    compile_masscan()
    copy_masscan()
    configure_masscan()
    # don't worry about cleaning up the local masscan binary

@task
def reboot():
    "Reboot. Doesn't wait."
    sudo('shutdown -r 0')

@task(default=True)
#@roles('survey')
def configure_survey():
    "Run all configuration to set up survey slave"
    install_masscan()  # do this first because it uses local sudo

    install_debs()
    configure_upgrades()
    set_timezone()
    install_pip()
    install_tasa()
    configure_collectd()
    configure_nginx()

    reboot()


@task
@roles('survey')
def check_networking():
    sudo('ethtool -k eth0')
    sudo('ethtook -k eth1')

@task
def deploy_looksee():
    sudo('pip install -U pyrax')
    put('looksee')
