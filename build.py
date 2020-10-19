#!/usr/bin/env python

import boto3
import paramiko
import socket
import spur
import sys
import textwrap

from paramiko import BadHostKeyException, AuthenticationException, SSHException
from time import sleep

AMI_USER='arch'
PROFILE_NAME='etuttle-admin-r'
REGION_NAME='us-east-2'


def wait_ssh(ip, user, interval=5, retries=100):
    print "Waiting for SSH connection to %s" % hostname

    for x in range(retries):
        try:
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            return ssh.connect(ip, username=user,
                               timeout=1.0,
                               banner_timeout=1.0,
                               auth_timeout=1.0)
        except (BadHostKeyException, AuthenticationException,
                SSHException, socket.error):
            sleep(interval)


session = boto3.session.Session(
    profile_name=PROFILE_NAME,
    region_name=REGION_NAME
)
ec2 = session.client('ec2')
instance_res = ec2.run_instances(KeyName='ethant',
                                 InstanceType='m5d.24xlarge',
                                 ImageId='ami-057b556e059980ae0',
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

print "Waiting for instance to start"
ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])

desc_res = ec2.describe_instances(InstanceIds=[instance_id])
hostname = desc_res['Reservations'][0]['Instances'][0]['PublicDnsName']
shell = None


def connect():
    global shell
    shell = spur.SshShell(hostname=hostname, username=AMI_USER, missing_host_key=spur.ssh.MissingHostKey.accept)


def run(cmd, **kwargs):
    shell.run(cmd, stdout=sys.stdout, stderr=sys.stderr, **kwargs)


try:
    wait_ssh(hostname, user=AMI_USER)
    connect()
    run(['sudo', 'pacman', '--noconfirm', '-Syu'])
    run(['sudo', 'pacman', '--noconfirm', '-Sy', 'git', 'base-devel', 'noto-fonts', 'python-pip'])
    run(['sudo', 'pip', 'install', 'awscli'])
    run(['sudo', 'reboot'], allow_error=True)

    wait_ssh(hostname, user=AMI_USER)
    connect()

    run(['git', 'clone', 'https://github.com/ungoogled-software/ungoogled-chromium-archlinux.git'])
    run(['makepkg', '-s', '--noconfirm'], cwd='${HOME}/ungoogled-chromium-archlinux')
    run(['/bin/sh', '-c', 'aws s3 cp --no-progress ungoogled-chromium-*.pkg.tar.zst s3://ethant-build-scratch/'],
        cwd='${HOME}/ungoogled-chromium-archlinux')
finally:
    ec2.terminate_instances(InstanceIds=[instance_id])

