#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
url handlers
'''

import re, time, json, logging, hashlib, base64, asyncio
from coroweb import get, post
from models import User, Blog, Comment, next_id

@get('/')
async def index(request):
    users = await User.findAll() # 调用某个表__table__的findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }