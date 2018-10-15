#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
编写一个辅助程序pymonitor.py，让它启动wsgiapp.py，并时刻监控www目录下的代码改动，
有改动时，先把当前wsgiapp.py进程杀掉，再重启，就完成了服务器进程的自动重启。

要监控目录文件的变化，我们也无需自己手动定时扫描，
Python的第三方库watchdog可以利用操作系统的API来监控目录文件的变化，并发送通知。

利用watchdog接收文件变化的通知，如果是.py文件，就自动重启wsgiapp.py进程。
利用Python自带的subprocess实现进程的启动和终止，并把输入输出重定向到当前进程的输入输出中
'''

import os, sys, time, subprocess

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def log(s):
    print('[Monitor] %s' % s)

class MyFileSystemEventHandler(FileSystemEventHandler):

    def __init__(self, fn):
        super(MyFileSystemEventHandler, self).__init__()
        self.restart = fn
    
    def on_any_event(self, event):
        # log('event.src_path: %s' % event.src_path)
        if event.src_path.endswith('.py'):  # 把这段代码的条件判断语句去掉就能自动重启了
            log('Python source file changed: %s' % event.src_path)
            self.restart()
# 改动.py文件后输出的event.src_path变量居然是www/.goutputstream-I3RZGY
# 不管什么文件，只要是改动过文件内容，event.src_path中都会带有.goutputstream，而I3RZGY似乎是个随机码，每次都不一样

command = ['echo', 'ok']
process = None

def kill_process():
    global process
    if process:
        log('Kill process [%s]...' % process.pid)
        process.kill()
        process.wait()
        log('Process ended with code %s.' % process.returncode)
        process = None

def start_process():
    global process, command
    log('Start process %s...' % ' '.join(command))
    process = subprocess.Popen(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)

def restart_process():
    kill_process()
    start_process()

def start_watch(path, callback):
    observer = Observer()
    observer.schedule(MyFileSystemEventHandler(restart_process), path, recursive=True)
    observer.start()
    log('Watching directory %s...' % path)
    start_process()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == '__main__':
    argv = sys.argv[1:]
    if not argv:
        print('Usage: ./pymonitor your-script.py')
        exit(0)
    if argv[0] != 'python':
        argv.insert(0, 'python')
    command = argv
    path = os.path.abspath('.')
    start_watch(path, None)

'''
一共70行左右的代码，就实现了Debug模式的自动重新加载。用下面的命令启动服务器：

$ python pymonitor.py wsgiapp.py
或者给pymonitor.py加上可执行权限，启动服务器：

$ ./pymonitor.py app.py
'''