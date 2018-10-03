#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
a web framework
'''

'''
# inspect模块提供了一系列函数用于帮助使用自省，
# 1. 用于类型检查（是否是模块，框架，函数等）  
# 2. 获取对象信息（获取类或函数的参数的信息等）
# 3. 获取源码
# 4. 解析堆栈
'''

import asyncio, os, inspect, logging, functools

from urllib import parse
from aiohttp import web
from apis import APIError


# 要把一个函数映射为一个URL处理函数，我们先定义@get()装饰器
def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

'''
由于装饰器的加入导致解释器认为函数本身发生了改变，在某些情况下——比如测试时——会导致一些问题。
Python 通过 functool.wraps 为我们解决了这个问题：在编写装饰器时，在实现前加入 @functools.wraps(func) 可以保证装饰器不会对被装饰函数造成影响。
'''
# 这样，一个函数通过@get()的装饰就附带了URL信息。
# @post与@get定义类似。

def post(path):
    '''
    Define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator


# 定义一些RequestHandler需要用到的接口函数,用来处理request（从request获取参数）
def has_request_arg(fn):
    sig = inspect.signature(fn) # 获取fn的完整参数列表，如：(a, b=0)
    params = sig.parameters # 将获取到的参数列表整理成dict型的列表，如：[('a', <Parameter "a">), ('b', <Parameter "b=0">)]
    found = False
    for name, param in params.items(): # 这里name是b, param是b=0, 且name是str类型， param是inspect.Parameter类型
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
    return found

'''
param.kind 可能会是如下几种情况：（且都是在inspect.Parameter中定义的） 如：def fn(a, b=0, *c, d, e=1, **f):
sig = inspect.signature(fn) # sig 是 (a, b=0, *c, d, e=1, **f) ， sig的类型是 <class 'inspect.Signature'>
params = sig.parameters     # params 是 OrderedDict([('a', <Parameter "a">), ('b', <Parameter "b=0">), ('c', <Parameter "*c">), ('d', <Parameter "d">), ('e', <Parameter "e=1">), ('f', <Parameter "**f">)])
                            # params 的类型是 <class 'mappingproxy'>

1. POSITIONAL_OR_KEYWORD  ==>  参数列表中的第一个参数，普通参数（变量）a , 且param.default是空（<class 'inspect._empty'>）
2. POSITIONAL_OR_KEYWORD  ==>  参数列表中的第一个参数，普通有初始值的参数（变量）b=0, 且param.default是0
3. VAR_POSITIONAL         ==>  类似于 *c 这种参数（变量），且param.default是空（<class 'inspect._empty'>）
4. KEYWORD_ONLY           ==>  非第一个参数的普通参数（变量）d，且param.default是空（<class 'inspect._empty'>）
5. KEYWORD_ONLY           ==>  非第一个参数的普通有初始值的参数（变量）e=1, 且param.default是1
6. VAR_KEYWORD            ==>  类似于 **f 这种参数（变量），且param.default是空（<class 'inspect._empty'>）

'''

def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True
    return False

def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False

def get_required_kw_args(fn): # 请求数据的变量，一般只有变量名字，值为空
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


'''
定义RequestHandler

URL处理函数不一定是一个coroutine，因此我们用RequestHandler()来封装一个URL处理函数。

RequestHandler是一个类，由于定义了__call__()方法，因此可以将其实例视为函数。可执行的类实例‘就是’一个函数

RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，调用URL函数，
然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求：

调用add_route注册handler的时候，将RequestHandler实例一并注册进去

这里的fn就是注册的handler函数，调用handler的时候是 fn(request),所以request是传给fn的，__call__就是执行fn(request)之前先执行的内置函数，可以做一些预先的处理

在__call__中会根据解析fn参数(request)的情况，重新组织一个request 为 kw，且将kw传给fn，再次调用fn(**kw)

'''

class RequestHandler(object):
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    @asyncio.coroutine
    def __call__(self, request): # 这个request是什么？哪里传入的？猜测，应该是aiohttp这个server去调用已经注册好了的handler的时候，会把request传进去
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'): # 若ct是json
                    params = yield from request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params # kw 就是request转换为json的json
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'): # 若ct是表单form类型
                    params = yield from request.post() # 通过post方式获取数据
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)

# 接下来实现一些 add_ 函数
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add_static %s => %s' % ('/static/', path))

# 再编写一个add_route函数，用来注册一个URL处理函数：
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))

# 最后一步，把很多次add_route()注册的调用变成自动扫描：自动把handler模块的所有符合条件的函数注册了
def add_routes(app, module_name):
    n = module_name.rfind('.') # 在当前路径查找
    if n == (-1): # 若当前路径没找到，则调用 globals(),locals()进行查找
        mod = __import__(module_name, globals(),locals())
    else:
        name = module_name[n+1:] # 找到了，获取module的name
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'): # 跳过module_name module中以 _ 开始的属性
            continue
        fn = getattr(mod, attr)
        if callable(fn): # 若module_name中的该属性是可执行的
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path: # 若该可执行属性拥有 __method__ 和 __route__ 属性，说明是需要注册的handler函数，调用add_route进行注册
                add_route(app, fn)

# 最后，在app.py中加入middleware、jinja2模板和自注册的支持
'''
app = web.Application(loop=loop, middlewares=[
    logger_factory, response_factory
])
init_jinja2(app, filters=dict(datetime=datetime_filter))
add_routes(app, 'handlers')
add_static(app)
'''
# 有了这些基础设施，我们就可以专注地往handlers模块不断添加URL处理函数了，可以极大地提高开发效率。

