#!/usr/bin/env python
"""
This file includes tasa workers, and a cli for inserting jobs into a
survey queue.
"""

import argparse
import subprocess
import imp

from tasa.store import Queue
from tasa.worker import BaseWorker


class MasscanWorker(BaseWorker):
    qinput = Queue('masscan')
    qoutput = None

    def run(self, job):
        """ Job is in the form [seed, shards-string, port].
        e.g. [213850, '4/10', 80]
        """
        command = ['masscan',
                   '--seed', job[0],
                   '--shards', job[1],
                   '--ports', job[2],
                   ]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        for line in proc.stdout:
            yield line


def insert_job(config):
    pass

# Since this is used as both a module and a shell script...
if __name__ == '__main__':
    # Don't worry too closely about this junk for now. It's what
    # creates the CLI, and is ugly and long and documented here:
    # http://docs.python.org/2.7/library/argparse.html
    # For exploration and one-off data gathering, hardcode values
    # until you know you need them to be configurable.
    parser = argparse.ArgumentParser()
    parser.add_argument('--redis',
                        default='redis://localhost:6379/01',
                        help="Redis connection string in form: "
                        "redis://password@example.org:6379/0")
    subparsers = parser.add_subparsers(help="sub-command help.")

    # Create our job insertion subparser
    parser_insert = subparsers.add_parser('insert',
        help="Insert a masscan job for distributed processing.")
    parser_insert.set_defaults(func=insert_job)
    parser_insert.add_argument('port',
                        help="Port to scan. In one of the forms 80, 5000-6000,"
                        " or 80,5000,8001.")
    parser_insert.add_argument('--range', default='0.0.0.0/0',
                        help="IPv4 address or range to scan. One of "
                        "these forms: "
                        "192.0.2.34, "
                        "198.51.100.0-198.51.100.125, "
                        "or 203.0.113.0/24. "
                        "Default 0.0.0.0/0.")
    parser_insert.add_argument('--shards', default='200', type=int,
                        help="Number of shards to split the scan into. "
                        "Default 200.")

    # Create our job control subparser
    parser_job = subparsers.add_parser('wipe',
                                       help="Job control.")
    parser_job.set_defaults(func='wipe')
    parser_job.add_argument('--all', action='store_true',
                            help="Wipe all jobs from redis.")

    # Try to load a python config file in a slightly unorthodox fashion
    # TODO: Move this into tasa proper
    try:
        tasa_conf = imp.load_source('tasa.conf', '/etc/tasa/tasa.conf')
    except IOError:
        tasa_conf = argparse.Namespace()

    # Parse our arguments, overriding anything found in the
    # conf file
    args = parser.parse_args(namespace=tasa_conf)
    #from pprint import pprint
    #pprint(vars(args))
