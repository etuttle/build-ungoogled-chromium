#!/usr/bin/env python2
from __future__ import print_function

import aws
import os
import paramiko
import socket
import spur
import sys

from paramiko import BadHostKeyException, AuthenticationException, SSHException
from time import sleep


# https://github.com/ungoogled-software/ungoogled-chromium-archlinux.git
REPO_OWNER='ungoogled-software'
REPO_NAME='ungoogled-chromium-archlinux'
REPO_TAG='87.0.4280.88-3'
CLONE_DIR=REPO_NAME
KEY_NAME='ethant'


class ShellRunner():
    def __init__(self, ami_ssh_user='arch') -> None:
        super().__init__()
        self.shell = None
        self.ami_ssh_user = ami_ssh_user

    def connect(self, hostname, ip):
        self.hostname = hostname
        self.ip = ip
        self.shell = spur.SshShell(
            hostname = self.hostname,
            username = self.ami_ssh_user,
            missing_host_key = spur.ssh.MissingHostKey.accept)

    def wait_ssh(self, interval=5, retries=100):
        print("Waiting for SSH connection to %s" % self.hostname)

        while range(retries):
            try:
                ssh = paramiko.SSHClient()
                ssh.load_system_host_keys()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                return ssh.connect(hostname=self.ip, user=self.username,
                            timeout=1.0, banner_timeout=1.0, auth_timeout=1.0)
            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error):
                sleep(interval)

        # from the spur readme... give it a chance for shell commands to work round-trip in addition
        # to basic ssh access
        for i in range(1,3):
            try:
                self..connect(hostname)
                self.run(['echo', 'hello'])
                break
            except RuntimeError as e:
                self.shell.close()
                sleep(3)
                continue

    def run(self, cmd, **kwargs):
        self.shell.run(cmd,
            stdout=sys.stdout, stderr=sys.stderr,
            encoding='utf-8', **kwargs)


def main():
    try:
        ec2 = aws.client('ec2')
        hostname, instance_id = start_instance(ec2)
        wait_ssh(hostname, user=ssh_user)
        connect(hostname)
        run(['sudo', 'pacman', '--noconfirm', '-Syu'])
        run(['sudo', 'pacman', '--noconfirm', '-Sy', 'base-devel', 'git',
             'noto-fonts', 'python-pip', 'subversion']) 
        run(['sudo', 'pip', 'install', 'awscli'])
        run(['sudo', 'reboot'], allow_error=True)

        wait_ssh(hostname, user=ssh_user)

        run(["svn", "export", ("https://github.com/" +
            os.path.join(REPO_OWNER, REPO_NAME, "tags", REPO_TAG)), WORKING_COPY])
        run(['makepkg', '-s', '--noconfirm'], cwd="/home/arch/ungoogled-chromium-archlinux")
        run(['/bin/sh', '-c', 'aws s3 cp --no-progress \
                    ungoogled-chromium-*.pkg.tar.zst s3://ethant-build-scratch/'],
            cwd="/home/arch/ungoogled-chromium-archlinux")
    finally:
        ec2.terminate_instances(InstanceIds=[instance_id])


def start_instance(ec2):
    instance_res = \
        ec2.run_instances(KeyName='ethant',
            InstanceType='m5d.24xlarge',
            ImageId='ami-043b666ec218ceb75',
            MinCount=1,
            MaxCount=1,
            BlockDeviceMappings=[
                {'DeviceName': '/dev/sda1',
                'Ebs': {'VolumeSize': 100}}
            ],
            IamInstanceProfile={
                'Arn': 'arn:aws:iam::378308805141:instance-profile/instance-build-scratch'
            },
        )
    instance_id = instance_res['Instances'][0]['InstanceId']

    print("Waiting for instance to start")
    ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])

    desc_res = ec2.describe_instances(InstanceIds=[instance_id])
    hostname = desc_res['Reservations'][0]['Instances'][0]['PublicDnsName']
    return hostname, instance_id

main()
