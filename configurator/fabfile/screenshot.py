from fabric.api import *

env.use_ssh_config = True


@task
def install_looksee_deps():
    sudo('apt-get install build-essential python-dev libtiff4-dev '
         'libjpeg8-dev zlib1g-dev libfreetype6-dev liblcms1-dev '
	 'libwebp-dev tcl8.5-dev tk8.5-dev')
    sudo('pip install -U pillow tasa pyrax')


@task
def deploy_looksee():
    put('looksee')
