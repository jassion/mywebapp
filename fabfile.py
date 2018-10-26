#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
Deployment toolkit
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
env.hosts = ['192.168.56.1']

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
        run('mysqldump --user=%s --password=%s --skip-opt --add-drop-table --default-character-set=utf8 --quik jsnwebapp > %s' % (db_user, db_password, f))
        run('tar -czvf %s.tar.gz %s' % (f, f))
        get('%s.tar.gz' % f, '%s/backup/' % _current_path())
        run('rm -f %s' % f)
        run('rm -f %s.tar.gz' % f)


_TAR_FILE = 'dist-jsnwebapp.tar.gz'

def build():
    '''
    Build dist package.
    '''
    includes = ['static', 'templates', '*.py']
    excludes = ['test', '.*', '*.pyc', '*.pyo']
    local('rm -f dist/%s' % _TAR_FILE)
    with lcd(os.path.join(_current_path(), 'www')):
        cmd = ['tar', '--dereference', '-czvf', '../dist/%s' % _TAR_FILE]
        cmd.extend(['--exclude=\'%s\'' % ex for ex in excludes])
        cmd.extend(includes)
        local(' '.join(cmd))

def deploy():
    newdir = 'www-%s' % _now()

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
    newdir = 'www-%s' % datetime.now().strftime('%y-%m-%d_%H.%M.%S')
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