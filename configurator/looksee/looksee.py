#!/usr/bin/env python
"""
This file includes tasa workers, and a cli for inserting jobs into a
survey queue.
"""

import argparse
import imp
import re
import subprocess
import time
import socket

import pyrax

import tasa
from tasa.store import Queue, PickleQueue
from tasa.utils import iterit
from tasa.worker import BaseWorker


pyrax.set_setting("identity_type", "rackspace")
pyrax.set_setting("region", "ORD")


class MasscanWorker(BaseWorker):
    qinput = Queue('masscan')
    qoutput = Queue('masscan_out')

    def run(self, job):
        """ Job is in the form [seed, shards-string, port].
        e.g. [213850, '4/10', 80]
        """
        command = ['masscan',
                   '--seed', str(job[0]),
                   '--shards', str(job[1]),
                   '--ports', str(job[2]),
                   ]
        proc = subprocess.Popen(command,
                                stdout=subprocess.PIPE)
        for line in proc.stdout:
            match = re.match(
                'Discovered open port (\d+)/(\w+) on (\d+\.\d+\.\d+\.\d+)',
                line.strip())
            if match:
                yield match.groups()
        proc.wait()


class RFBFingerprinter(BaseWorker):
    qinput = Queue('masscan_out')
    qoutput = PickleQueue('rfb_print')

    def run(self, job):
        port, proto, ip = job
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        output = []
        try:
            s.connect((ip, int(port)))
            rfb_proto = s.recv(512)
            output.append(rfb_proto)
            # mirror the specified protocol back to the sender
            s.sendall(rfb_proto)
            security_proto = s.recv(512)
            output.append(security_proto)
            if rfb_proto != 'RFB 003.003\n':
                s.sendall('\x01')  # try no security
                follow_data = s.recv(512)
                output.append(follow_data)
            s.close()
        except Exception:
            # Bad practice to catch all exceptions, but this is demo code...
            pass

        if output:
            # (ip, port, rfb_proto, security_proto, follow_data)
            yield [ip, port] + output


class ScreenshotWorker(BaseWorker):
    qinput = PickleQueue('rfb_print')
    qoutput = Queue('taken_screenshots')

    def __init__(self, *args, **kwargs):
        super(ScreenshotWorker, self).__init__(*args, **kwargs)
        pyrax.set_credentials(tasa.conf.rax_username,
                              tasa.conf.rax_password)

    def run(self, job):
        ip = job[0]
        port = job[1]
        screen = str(int(port) - 5900)
        try:
            security_protos = job[3][1:]
        except IndexError:
            # don't do anything if we don't have the info we want for now
            return
        # can we authenticate with no password?
        if '\x01' in security_protos:
            # then let's try taking a picture
            command = ['vncsnapshot',
                       '-passwd', '/dev/null',  # fail if passwd reqested
                       '-quality', '70',
                       '-vncQuality', '7',
                       ':'.join([ip, screen]),
                       '-',  # output screenshot jpeg to stdout
                       ]
            proc = subprocess.Popen(command,
                                    stdout=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            # desktop_name = re.match('Desktop name "(.*)"\n', stderr)
            # if desktop_name:
            #     name = desktop_name.groups()[0]
            # else:
            #     name = ''
            if stdout:
                # store our result in the cloud
                container = ip.split('.')[0]
                file_name = ip + '_' + port + '.jpg'
                print container, file_name
                exit
                pyrax.cloudfiles.store_object(container,
                                              file_name,
                                              stdout,
                                              content_type="image/jpeg")
                connection = tasa.store.connection
                connection.hset('container_' + container, file_name, stderr)


def insert_job():
    """ Write job shards into redis. """
    seed = str(int(time.time()))  # round it
    total_shards = tasa.conf.shards
    jobs = []
    for shard in range(1, total_shards + 1):
        jobs.append(
            [seed, '%d/%d' % (shard, total_shards), tasa.conf.ports])
    MasscanWorker.qinput.send(*jobs)


def create_containers():
    """Create the containers where result files will be stored. Delete any
    existing contents.
    """
    print "Creating clean result containers. This may take a while..."
    pyrax.set_credentials(tasa.conf.rax_username,
                          tasa.conf.rax_password)
    connection = tasa.store.connection
    # create a set of the containers in which we will be storing results
    for subnet in range(0, 256):
        cont_name = str(subnet)
        container = pyrax.cloudfiles.create_container(cont_name)
        pyrax.cloudfiles.make_container_public(container)
#        container.delete_all_objects()  # this takes too long
        connection.hset('container_uris', cont_name, container.cdn_uri)
        print "Created container: ", subnet
    print "Finished creating containers."


def render_output_website():
    """ Render the output template website.

    This is messy last minute code. Sorry :(
    """
    from jinja2 import Environment, PackageLoader
    env = Environment(loader=PackageLoader('looksee', 'templates'))
    connection = tasa.store.connection
    containers = {}
    uris = connection.hgetall('container_uris')
    for key, value in uris.items():
        containers[key] = {'uri': value}
    pipe = connection.pipeline()
    for key in uris.keys():
        pipe.hgetall('container_' + key)
    for key, value in zip(uris.keys(), pipe.execute()):
        containers[key]['files'] = value
    template = env.get_template('container_index.html')
    rendered = template.render(containers=containers)
    with open('www/index.html', 'w') as f:
        f.write(rendered)
    template = env.get_template('inner_index.html')
    for key in containers.keys():
        rendered = template.render(base_uri=containers[key]['uri'],
                                   files = containers[key]['files'])
        with open('www/%s.html' % key, 'w') as f:
            f.write(rendered)

# Since this is used as both a module and a shell script, only parse
# arguments if it is called directly...
if __name__ == '__main__':
    # Don't worry too closely about this junk for now. It's what
    # creates the CLI, and is ugly and long and documented here:
    # http://docs.python.org/2.7/library/argparse.html
    # For exploration and one-off data gathering, hardcode values
    # until you know they need to be configurable.
    parser = argparse.ArgumentParser()
    # parser.add_argument('--redis',
    #                     default='redis://localhost:6379/0',
    #                     help="Redis connection string in form: "
    #                     "redis://password@example.org:6379/0")
    subparsers = parser.add_subparsers(help="sub-command help.")

    # Create our job insertion subparser
    parser_insert = subparsers.add_parser('insert',
        help="Insert a masscan job for distributed processing.")
    parser_insert.set_defaults(func=insert_job)
    parser_insert.add_argument('ports',
                        help="Ports to scan. In one of the forms 80, 5000-6000,"
                        " or 80,5000,8001.")
    parser_insert.add_argument('--range', default='0.0.0.0/0',
                        help="IPv4 address or range to scan. One of "
                        "these forms: "
                        "192.0.2.34, "
                        "198.51.100.0-198.51.100.125, "
                        "or 203.0.113.0/24. "
                        "Default 0.0.0.0/0.")
    parser_insert.add_argument('--shards', default='100', type=int,
                        help="Number of shards to split the scan into. "
                        "Default 100.")

#    # Create our job control subparser
#    parser_job = subparsers.add_parser('wipe',
#                                       help="Job control.")
#    parser_job.set_defaults(func='wipe')
#    parser_job.add_argument('--all', action='store_true',
#                            help="Wipe all jobs from redis.")

    # Create our cloudfiles containers
    parser_job = subparsers.add_parser('create_containers',
                                       help="Create cloudfiles containers "
                                       "and remove any existing content.")
    parser_job.set_defaults(func=create_containers)


    parser_job = subparsers.add_parser('render_output')
    parser_job.set_defaults(func=render_output_website)


    # Parse our arguments, overriding anything found in the
    # conf file
    parser.parse_args(namespace=tasa.conf)
    tasa.conf.func()
