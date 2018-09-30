#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
async web application
'''

import logging; logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime

from aiohttp import web

from jinja2 import Environment, FileSystemLoader
import orm
from coroweb import add_routes, add_static

# jinja2是模板引擎，主要是对模板的配置和使用
def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape = kw.get('autoescape', True),
        block_start_string = kw.get('block_start_string', '{%'),
        block_end_string = kw.get('block_end_string', '%}'),
        variable_start_string = kw.get('variable_start_string', '{{'),
        variable_end_string = kw.get('variable_end_string', '}}'),
        auto_reload = kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
    logging.info('set jinja2 template path: %s' % path)
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env # 将配置好的模板使用环境传给app的'__templating__'属性

async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        # await asyncio.sleep(0.3)
        return (await handler(request))
    return logger

async def data_factory(app, handler):
    async def parse_data(request): # 解析request，将解析得到的数据放在request的__data__属性中
        if request.method == 'POST':
            if request.content_type.startswith('application/json'): # 若request的content_type是json，则用request.json()来解析
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'): # 若request的content_type是x-www-form-urlencoded，则用request.post()来解析
                request.__data__ = await request.post()
                logging.info('request form: %s' % str(request.__data__))
        return (await handler(request))
    return parse_data

'''
response_factory生成响应response，并返回，交给aiohttp server去发送给请求者
根据 handler(request)返回的结果来判断如何生成需要的响应response
'''
async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
#            if r == '/':
#                return web.Response(body=b'<h1>Awesome</h1>', content_type='text/html')
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict): # 主要返回的大部分是dict，执行该项
            template = r.get('__template__') # 获取handler返回的dict中的__template__属性
            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8')) # 从配置好的template环境中获取对应的template
                resp.content_type = 'text/html;charset=utf-8' # jinja2的Environment对象通过get_template(template)获取一个具体的模板文件，
                return resp      # 模板文件通过.render(params)接收参数，并且对模板进行渲染，这里的渲染就是将模板中对应的变量根据传入的参数进行赋值处理成静态的html文件
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        # default: 将r当作str处理
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response

def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 60*60:
        return u'%s分钟前' % (delta // 60)
    if delta < 60*60*24:
        return u'%s小时前' % (delta // (60*60))
    if delta < 60*60*24*365:
        return u'%s天前' % (delta // (60*60*24))
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)

def index(request):
    return web.Response(body=b'<h1>Awesome</h1>', content_type='text/html')


async def init(loop):
    await orm.create_pool(loop=loop, host='127.0.0.1', port=3308, user='www-data', password='www-data', database='db_web')
    app = web.Application(loop=loop, middlewares=[
        logger_factory,
        response_factory
    ])
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')
    add_static(app)
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000...')
    return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()


