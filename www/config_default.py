#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
default configuration
'''
configs = {
    'debug': True,
    'db': {
        'host': '127.0.0.1',
        'port': 3308,
        'user': 'www-data',
        'password': 'www-data',
        'database': 'db_web'
    },
    'session': {
        'secret': 'jAsSIoN'
    }
}
