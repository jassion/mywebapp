#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
Deployment toolkit
'''
'''
Fabric就是一个自动化部署工具。由于Fabric是用Python 2.x开发的，所以，部署脚本要用Python 2.7来编写，
本机还必须安装Python 2.7版本。

要用Fabric部署，需要在本机（是开发机器，不是Linux服务器）安装Fabric：
$ easy_install fabric

Linux服务器上不需要安装Fabric，Fabric使用SSH直接登录服务器并执行部署命令。
'''

import os, re
from datetime import datetime

# 导入Fabric API：
from fabric.api import *


# 服务器登录用户名：
env.user = 'jsn'
# sudo用户为root:
env.sudo_user = 'root'
# 服务器地址，可以有多个，依次部署：
env.hosts = ['10.28.120.60']

# 服务器Mysql用户名和口令：
db_user = 'www-data'
db_password = 'www-data'

def _current_path():
    return os.path.abspath('.')

def _now():
    return datetime.now().strftime('%y-%m-%d_%H.%M.%S')


# 每个Python函数都是一个任务:
def backup():
    '''
    Dump entrie database on server and backup to local.
    '''
    dt = _now()
    f = 'backup-jsnwebapp-%s.sql' % dt
    with cd('/tmp'):
        run('mysqldump --user=%s --password=%s --skip-opt --add-drop-table --default-character-set=utf8 --quik db_web > %s' % (db_user, db_password, f))
        run('tar -czvf %s.tar.gz %s' % (f, f))
        get('%s.tar.gz' % f, '%s/backup/' % _current_path())
        run('rm -f %s' % f)
        run('rm -f %s.tar.gz' % f)


_TAR_FILE = 'dist-jsnwebapp.tar.gz'

def build():
    '''
    Build dist package.
    '''
    includes = ['static', 'templates', 'favicon.ico', '*.py']
    excludes = ['test', '.*', '*.pyc', '*.pyo']
    local('rm -f dist/%s' % _TAR_FILE)
    with lcd(os.path.join(_current_path(), 'www')):
        cmd = ['tar', '--dereference', '-czvf', '../dist/%s' % _TAR_FILE]
        cmd.extend(['--exclude=\'%s\'' % ex for ex in excludes])
        cmd.extend(includes)
        local(' '.join(cmd))


'''
Fabric提供local('...')来运行本地命令，with lcd(path)可以把当前命令的目录设定为lcd()指定的目录，
注意Fabric只能运行命令行命令，Windows下可能需要Cgywin环境。
在webapp目录下运行：
$ fab build
看看是否在dist目录下创建了.tar.gz的文件。
'''

# 打包后，我们就可以继续编写deploy任务，把打包文件上传至服务器，解压，重置www软链接，重启相关服务：

_REMOTE_TMP_TAR = '/tmp/%s' % _TAR_FILE
_REMOTE_BASE_DIR = '/srv/jsnwebapp'

def deploy():
    newdir = 'www-%s' % _now()
    # 删除已有的tar文件:
    run('rm -f %s' % _REMOTE_TMP_TAR)
    # 上传新的tar文件:
    put('dist/%s' % _TAR_FILE, _REMOTE_TMP_TAR)
    # 创建新目录:
    with cd(_REMOTE_BASE_DIR):
        sudo('mkdir %s' % newdir)
    # 解压到新目录:
    with cd('%s/%s' % (_REMOTE_BASE_DIR, newdir)):
        sudo('tar -xzvf %s' % _REMOTE_TMP_TAR)
    # 重置软链接:
    with cd(_REMOTE_BASE_DIR):
        sudo('rm -f www')
        sudo('ln -s %s www' % newdir)
        sudo('chown www-data:www-data www')
        sudo('chown -R www-data:www-data %s' % newdir)
    # 重启Python服务和nginx服务器:
    with settings(warn_only=True):
        sudo('supervisorctl stop jsnwebapp')
        sudo('supervisorctl start jsnwebapp')
        sudo('/etc/init.d/nginx reload')
'''
注意run()函数执行的命令是在服务器上运行，with cd(path)和with lcd(path)类似，
把当前目录在服务器端设置为cd()指定的目录。如果一个命令需要sudo权限，就不能用run()，而是用sudo()来执行。
'''

RE_FILES = re.compile('\r?\n')

def rollback():
    '''
    rollback to previous version
    '''
    with cd(_REMOTE_BASE_DIR):
        r = run('ls -p -1')
        files = [s[:-1] for s in RE_FILES.split(r) if s.startswith('www-') and s.endswith('/')]
        files.sort(cmp=lambda s1, s2: 1 if s1 < s2 else -1)
        r = run('ls -l www')
        ss = r.split(' -> ')
        if len(ss) != 2:
            print('ERROR: \'www\' is not a symbol link.')
            return
        current = ss[1]
        print('Found current symbol link points to: %s\n' % current)
        try:
            index = files.index(current)
        except ValueError as e:
            print('ERROR: symbol link is invalid.')
            return
        if len(files) == index + 1:
            print('ERROR: already the oldest version.')
        old = files[index + 1]
        print('===================================================')
        for f in files:
            if f == current:
                print('       Current ---> %s' % current)
            elif f == old:
                print('   Rollback to ---> %s' % old)
            else:
                print('                    %s' % f)
        print('===================================================')
        print('')
        yn = raw_input('continue? y/N ')
        if yn != 'y' and yn != 'Y':
            print('Rollback cancelled.')
            return
        print('Start rollback...')
        sudo('rm -f www')
        sudo('ln -s %s www' % old)
        sudo('chown www-data:www-data www')
        with settings(warn_only=True):
            sudo('supervisorctl stop jsnwebapp')
            sudo('supervisorctl start jsnwebapp')
            sudo('/etc/init.d/nginx reload')
        print('ROLLBACKED OK.')

def restore2local():
    '''
    Restore db to local
    '''
    backup_dir = os.path.join(_current_path(), 'backup')
    fs = os.listdir(backup_dir)
    files = [f for f in fs if f.startswith('backup-') and f.endswith('.sql.tar.gz')]
    files.sort(cmp=lambda s1, s2: 1 if s1 < s2 else -1)
    if len(files)==0:
        print('No backup files found.')
        return
    print('Found %s backup files:' % len(files))
    print('=================================================')
    n = 0
    for f in files:
        print('%s: %s' % (n, f))
        n = n + 1
    print('=================================================')
    print('')
    try:
        num = int(raw_input('Restore file: '))
    except ValueError:
        print('Invalid file number.')
        return
    restore_file = files[num]
    yn = raw_input('Restore file %s: %s? y/N' % (num, restore_file))
    if yn != 'y' and yn != 'Y':
        print('Restore cancelled.')
        return
    print('Start restore to local database...')
    p = raw_input('Input mysql root password: ')
    sqls = [
        'drop database if exists db_web;',
        'create database db_web;',
        'grant select, insert, update, delete on db_web.* to \'%s\'@\'localhost\' identified by \'%s\';' % (db_user, db_password)
    ]
    for sql in sqls:
        local(r'mysql -u root -p%s -e "%s"' % (p, sql))
    with lcd(backup_dir):
        local('tar -zxvf %s' % restore_file)
    local(r'mysql -u root -p%s db_web < backup/%s' % (p, restore_file[:-7]))
    with lcd(backup_dir):
        local('rm -f %s' % restore_file[:-7])


'''
配置Supervisor
上面让Supervisor重启jsnwebapp的命令会失败，因为我们还没有配置Supervisor呢。

编写一个Supervisor的配置文件jsnwebapp.conf，存放到/etc/supervisor/conf.d/目录下：

[program:jsnwebapp]

command     = /srv/jsnwebapp/www/app.py
directory   = /srv/jsnwebapp/www
user        = www-data
startsecs   = 3

redirect_stderr         = true
stdout_logfile_maxbytes = 50MB
stdout_logfile_backups  = 10
stdout_logfile          = /srv/jsnwebapp/log/app.log
配置文件通过[program:jsnwebapp]指定服务名为jsnwebapp，command指定启动app.py。

然后重启Supervisor后，就可以随时启动和停止Supervisor管理的服务了：

$ sudo supervisorctl reload
$ sudo supervisorctl start jsnwebapp
$ sudo supervisorctl status
jsnwebapp                RUNNING    pid 1401, uptime 5:01:34
'''

'''
配置Nginx
Supervisor只负责运行app.py，我们还需要配置Nginx。把配置文件jsnwebapp放到/etc/nginx/sites-available/目录下：

server {
    listen      80; # 监听80端口

    root       /srv/jsnwebapp/www;
    access_log /srv/jsnwebapp/log/access_log;
    error_log  /srv/jsnwebapp/log/error_log;

    # server_name awesome.liaoxuefeng.com; # 配置域名

    # 处理静态文件/favicon.ico:
    #location /favicon.ico {
    #    root /srv/jsnwebapp/www;
    #}

    # 处理静态资源:
    location ~ ^\/static\/.*$ {
        root /srv/jsnwebapp/www;
    }

    # 动态请求转发到9000端口:
    location / {
        proxy_pass       http://127.0.0.1:9000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
然后在/etc/nginx/sites-enabled/目录下创建软链接：

$ pwd
/etc/nginx/sites-enabled
$ sudo ln -s /etc/nginx/sites-available/jsnwebapp .
让Nginx重新加载配置文件，不出意外，我们的jsnwebapp应该正常运行：

$ sudo /etc/init.d/nginx reload
如果有任何错误，都可以在/srv/jsnwebapp/log下查找Nginx和App本身的log。如果Supervisor启动时报错，可以在/var/log/supervisor下查看Supervisor的log。

如果一切顺利，你可以在浏览器中访问Linux服务器上的jsnwebapp了;

--------------------------------------------------------------
如果在开发环境更新了代码，只需要在命令行执行：
$ fab build
$ fab deploy
自动部署完成！刷新浏览器就可以看到服务器代码更新后的效果。
'''