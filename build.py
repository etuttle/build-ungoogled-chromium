#!/usr/bin/env python

import boto3
import paramiko
import socket
import spur
import sys
import textwrap

from paramiko import BadHostKeyException, AuthenticationException, SSHException
from time import sleep


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


session = boto3.session.Session(profile_name='ethan')
ec2 = session.client('ec2')
instance_res = ec2.run_instances(KeyName='ethant',
                                 InstanceType='m5d.24xlarge',
                                 ImageId='ami-00031286724f9b660',
                                 MinCount=1,
                                 MaxCount=1,
                                 BlockDeviceMappings=[
                                     {'DeviceName': '/dev/sda1',
                                      'Ebs': {'VolumeSize': 100}}
                                 ],
                                 IamInstanceProfile={
                                     'Arn': 'arn:aws:iam::378308805141:instance-profile/build-instance'
                                 },
                                 UserData=textwrap.dedent("""\
                                 #!/bin/bash
                                 useradd -m ec2-user
                                 install -d -o ec2-user -g ec2-user -m 0700 /home/ec2-user/.ssh
                                 install -o ec2-user /root/.ssh/authorized_keys /home/ec2-user/.ssh/authorized_keys
                                 echo "ec2-user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
                                 """))
instance_id = instance_res['Instances'][0]['InstanceId']

print "Waiting for instance to start"
ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])

desc_res = ec2.describe_instances(InstanceIds=[instance_id])
hostname = desc_res['Reservations'][0]['Instances'][0]['PublicDnsName']
shell = None


def connect():
    global shell
    shell = spur.SshShell(hostname=hostname, username='ec2-user', missing_host_key=spur.ssh.MissingHostKey.accept)


def run(cmd, **kwargs):
    shell.run(cmd, stdout=sys.stdout, stderr=sys.stderr, **kwargs)


try:
    wait_ssh(hostname, user='ec2-user')
    connect()
    run(['sudo', 'pacman', '--noconfirm', '-Syu'])
    run(['sudo', 'pacman', '--noconfirm', '-Sy', 'git', 'base-devel', 'noto-fonts', 'python-pip'])
    run(['sudo', 'pip', 'install', 'awscli'])
    run(['sudo', 'reboot'], allow_error=True)

    wait_ssh(hostname, user='ec2-user')
    connect()
    run(['git', 'clone', 'https://aur.archlinux.org/libglvnd-glesv2.git'])
    run(['makepkg', '-s', '--noconfirm'], cwd='/home/ec2-user/libglvnd-glesv2')
    run(['sh', '-c', 'yes | sudo pacman -U /home/ec2-user/libglvnd-glesv2/libglvnd-glesv2*.pkg.tar.xz'])

    run(['git', 'clone', 'https://github.com/ungoogled-software/ungoogled-chromium-archlinux.git'])
    run(['makepkg', '-s', '--noconfirm'], cwd='/home/ec2-user/ungoogled-chromium-archlinux')
    run(['/bin/sh', '-c', 'aws s3 cp --no-progress ungoogled-chromium-*.pkg.tar.xz s3://ethant-build-scratch/'],
        cwd='/home/ec2-user/ungoogled-chromium-archlinux')
finally:
    ec2.terminate_instances(InstanceIds=[instance_id])