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
from base64 import b64encode
import socket


import tasa
from tasa.store import Queue, PickleQueue
from tasa.utils import iterit
from tasa.worker import BaseWorker


class MasscanWorker(BaseWorker):
    qinput = Queue('masscan')
    qoutput = Queue('masscan_out')

    def run(self, job):
        """ Job is in the form [seed, shards-string, port].
        e.g. [213850, '4/10', 80]
        """
        command = ['masscan',
                   '--seed', job[0],
                   '--shards', job[1],
                   '--ports', job[2],
                   ]
        proc = subprocess.Popen(iterit(command, cast=str),
                                stdout=subprocess.PIPE)
        for line in proc.stdout:
            match = re.match(
                'Discovered open port (\d+)/(\w+) on (\d+\.\d+\.\d+\.\d+)',
                line.strip())
            if match:
                yield match.groups()


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
                s.sendall('\x01')  # try no security, regardless of choices
                follow_data = s.recv(512)
                output.append(follow_data)
            s.close()
        except Exception:
            pass

        if output:
            # (ip, port, rfb_proto, security_proto, follow_data)
            yield [ip, port] + apply(b64encode, output)


def insert_job():
    seed = int(time.time())
    total_shards = tasa.conf.shards
    jobs = []
    for shard in range(1, total_shards + 1):
        jobs.append(
            [seed, '%d/%d' % (shard, total_shards), tasa.conf.ports])
    MasscanWorker.qinput.send(*jobs)


# Since this is used as both a module and a shell script, only parse
# arguments if it is called directly...
if __name__ == '__main__':
    # Don't worry too closely about this junk for now. It's what
    # creates the CLI, and is ugly and long and documented here:
    # http://docs.python.org/2.7/library/argparse.html
    # For exploration and one-off data gathering, hardcode values
    # until you know they need to be configurable.
    parser = argparse.ArgumentParser()
    parser.add_argument('--redis',
                        default='redis://localhost:6379/0',
                        help="Redis connection string in form: "
                        "redis://password@example.org:6379/0")
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

    # Create our job control subparser
    parser_job = subparsers.add_parser('wipe',
                                       help="Job control.")
    parser_job.set_defaults(func='wipe')
    parser_job.add_argument('--all', action='store_true',
                            help="Wipe all jobs from redis.")

    # Parse our arguments, overriding anything found in the
    # conf file
    parser.parse_args(namespace=tasa.conf)
    #from pprint import pprint
    #pprint(vars(tasa.conf))
    tasa.conf.func()
