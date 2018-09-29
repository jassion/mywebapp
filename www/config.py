#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
generate configuration
'''
import config_default

configs = config_default.configs

class Dict(dict):
    '''
    Simple dict but support access as x.y style.
    '''
    def __init__(self, names=(), values=(), **kw):
        super(Dict,self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

def merge(defaults, override):
    r = {}
    for k, v in defaults.items():
        if k in override: # k在override里面，需要merge，就是以override中的值为主
            if isinstance(v, dict): # 若v还是一个dict，则继续迭代处理该dict
                r[k] = merge(v, override[k])
            else: # 进行merge处理，就是取override中的值为最终值
                r[k] = override[k]
        else: # k不在override中，说明只在default中存在，则保留该项
            r[k] = v
    return r

def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v # 若v还是dict，则迭代，全部转为Dict
    return D

configs = config_default.configs

try:
    import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    pass

# print(configs)
# print(configs.db)  # Fail

configs = toDict(configs)

# print(configs.db) # Pass
# username = configs.db.user
# print('toDict:',username) # Pass