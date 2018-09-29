#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
Web App里面有很多地方都要访问数据库。访问数据库需要创建数据库连接、游标对象，然后执行SQL语句，最后处理异常，清理资源。这些访问数据库的代码如果分散到各个函数中，势必无法维护，也不利于代码复用。

所以，我们要首先把常用的SELECT、INSERT、UPDATE和DELETE操作用函数封装起来。

由于Web框架使用了基于asyncio的aiohttp，这是基于协程的异步模型。在协程中，不能调用普通的同步IO操作，因为所有用户都是由一个线程服务的，协程的执行速度必须非常快，才能处理大量用户的请求。而耗时的IO操作不能在协程中以同步的方式调用，否则，等待一个IO操作时，系统无法响应任何其他用户。

这就是异步编程的一个原则：一旦决定使用异步，则系统每一层都必须是异步，“开弓没有回头箭”。

幸运的是aiomysql为MySQL数据库提供了异步IO的驱动。
'''

import asyncio, logging
import aiomysql

# 一次使用异步 处处使用异步

def loginfo(sql, args=()):
    logging.info('SQL: %s' % sql)


'''
创建连接池

我们需要创建一个全局的连接池，每个HTTP请求都可以从连接池中直接获取数据库连接。使用连接池的好处是不必频繁地打开和关闭数据库连接，而是能复用就尽量复用。

连接池由全局变量__pool存储，缺省情况下将编码设置为utf8，自动提交事务：
aiomysql：https://aiomysql.readthedocs.io/en/latest/tutorial.html
'''
@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = yield from aiomysql.create_pool( # yield from 将会调用一个子协程，并直接返回调用的结果
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3308),
        user=kw['user'],
        password=kw['password'],
        db=kw['database'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )

@asyncio.coroutine
def destroy_pool():
    global __pool
    if __pool is not None: # 通过aiomysql.create_pool创建的pool都具有如下的功能，且如下是标准的关闭Pool的步骤
        __pool.close()
        yield from __pool.wait_closed()



'''
Select

要执行SELECT语句，我们用select函数执行，需要传入SQL语句和SQL参数

SQL语句的占位符是?，而MySQL的占位符是%s，select()函数在内部自动替换。注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串，这样可以防止SQL注入攻击。

注意到yield from将调用一个子协程（也就是在一个协程中调用另一个协程）并直接获得子协程的返回结果。

如果传入size参数，就通过fetchmany()获取最多指定数量的记录，否则，通过fetchall()获取所有记录。
'''
@asyncio.coroutine
def select(sql, args, size=None): # 全局对象（实例）的select()，传进来的sql就是一条完整的sql语句，args是在sql语句中占位符对应的数值数据
    loginfo(sql, args)
    global __pool
    with (yield from __pool) as conn:
        cur = yield from conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?', '%s'), args or ()) # 将sql语句的占位符？替换为所使用的数据库Mysql的占位符%s，然后执行该sql语句
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

'''
Insert, Update, Delete

要执行INSERT、UPDATE、DELETE语句，可以定义一个通用的execute()函数，因为这3种SQL的执行都需要相同的参数，以及返回一个整数表示影响的行数
execute()函数和select()函数所不同的是，cursor对象不返回结果集，而是通过rowcount返回结果数
'''
async def execute(sql, args, autocommit=True):  # 全局对象（实例）的execute()
    loginfo(sql, args)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin() # 若是不允许autocommit，则在开始处标记此次connection的位置，为了之后的回滚操作rollback所做的标记
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            if autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected

# 生成num个“?”,并且以“,”分割，生成对应与sql语句args参数中参数个数的占位符
# 比如说：insert into  `User` (`password`, `email`, `name`, `id`) values (?,?,?,?) 
def create_args_string(num): 
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)

# 构造Field 和各种Field子类，Field指的是Mysql中的数据存储类型,它负责保存数据库表的字段名和字段类型
class Field(object):  # 在Mysql中，每一个Field都是一行，每一行都包含了如下4个属性(列)+另外的2项属性(列)：NULL、Extra
    def __init__(self, name, column_type, primary_key, default): # 对比Mysql中desc指令（desc tablename;）产看的数据表信息，还有2项属性分别是：NULL， Extra
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self): # 以string类型返回对应的Field基本信息： <类的名字（表的名字）， 数据类型（字段名）：数据名称（具体的字段类型名称）>
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name) 

# 映射varchar的StringField：
class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'): # ddl定义了类型，相当于column_type
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default) # boolen类型不可以作为PK，PK：Primary Key

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default) # Text类型不可以作为PK


# 在python中，类（class）也是对象，可以当作对象来处理，拥有对象拥有的所有属性，所以可以在运行时使用class关键字动态创建类
# type函数也可以动态创建类，其语法：type(类名, 父类的元组（针对继承的情况，可以为空），包含属性的字典（名称和值）)
# 例：Foo = type('Foo', (), {'bar':True})  # 创建 类Foo，没有继承，有一个属性bar，值为True
# 例：FooChild = type('FooChild', (Foo,),{}) # 创建 类FooChild，继承自Foo，无属性
# 例：FooChild = type('FooChild', (Foo,), {'echo_bar': echo_bar}) # 创建 类FooChild， 继承自Foo，添加属性echo_bar，值为echo_bar


# MetaClass 是指元类：元类就是类的类，因为在python中类也是对象，元类就是用来创建这些类（对象）的，type就是Python在背后用来创建所有类的元类
# MyClass = MetaClass() # 元类创建出类MyClass ，这里MyClass就是通过type()来创建的类，它是type()类的一个实例，函数type()实际上就是一个元类
# MyObject = MyClass() # 类创建出实例MyObject
# 在写一个类的时候为其添加__metaclass__属性,定义了__metaclass__就定义了这个类的元类。
'''
class Foo(object):   #py2
    __metaclass__ = something…


class Foo(metaclass=something):   #py3
    __metaclass__ = something…

现在的问题就是，你可以在__metaclass__中放置些什么代码呢？
答案就是：可以创建一个类的东西。那么什么可以用来创建一个类呢？type，或者任何使用到type或者子类化type的东西都可以。
'''
# 创建元类也可以通过继承type来实现：class Foo(type):,类Foo就是一个元类了
'''
元类的主要目的就是为了当创建类时能够自动地改变类。通常，你会为API做这样的事情，你希望可以创建符合当前上下文的类。
假想一个很傻的例子，你决定在你的模块里所有的类的属性都应该是大写形式。有好几种方法可以办到，但其中一种就是通过设定__metaclass__。
采用这种方法，这个模块中的所有类都会通过这个元类来创建，我们只需要告诉元类把所有的属性都改成大写形式就万事大吉了。

1. 使用函数作为元类
# 元类会自动将你通常传给‘type’的参数作为自己的参数传入
def upper_attr(future_class_name, future_class_parents, future_class_attr):
    '返回一个类对象，将属性都转为大写形式
    #选择所有不以'__'开头的属性
    attrs = ((name, value) for name, value in future_class_attr.items() if not name.startswith('__'))
    # 将它们转为大写形式
    uppercase_attr = dict((name.upper(), value) for name, value in attrs)
    #通过'type'来做类对象的创建
    return type(future_class_name, future_class_parents, uppercase_attr)#返回一个类

class Foo(object):
    __metaclass__ = upper_attr
    bar = 'bip' 

>>
print hasattr(Foo, 'bar')
# 输出: False
print hasattr(Foo, 'BAR')
# 输出:True
 
f = Foo()
print f.BAR
# 输出:'bip'

2. 使用class来当做元类
# 请记住，'type'实际上是一个类，就像'str'和'int'一样。所以，你可以从type继承
# __new__ 是在__init__之前被调用的特殊方法，__new__是用来创建对象并返回之的方法，__new_()是一个类方法
# 而__init__只是用来将传入的参数初始化给对象，它是在对象创建之后执行的方法。
# 你很少用到__new__，除非你希望能够控制对象的创建。这里，创建的对象是类，我们希望能够自定义它，所以我们这里改写__new__
# 如果你希望的话，你也可以在__init__中做些事情。还有一些高级的用法会涉及到改写__call__特殊方法，但是我们这里不用，下面我们可以单独的讨论这个使用

class UpperAttrMetaClass(type):
    def __new__(upperattr_metaclass, future_class_name, future_class_parents, future_class_attr):
        attrs = ((name, value) for name, value in future_class_attr.items() if not name.startswith('__'))
        uppercase_attr = dict((name.upper(), value) for name, value in attrs)
        return type(future_class_name, future_class_parents, uppercase_attr)#返回一个对象，但同时这个对象是一个类
但是，这种方式其实不是OOP。我们直接调用了type，而且我们没有改写父类的__new__方法。现在让我们这样去处理:
class UpperAttrMetaclass(type):
    def __new__(upperattr_metaclass, future_class_name, future_class_parents, future_class_attr):
        attrs = ((name, value) for name, value in future_class_attr.items() if not name.startswith('__'))
        uppercase_attr = dict((name.upper(), value) for name, value in attrs)
 
        # 复用type.__new__方法
        # 这就是基本的OOP编程，没什么魔法。由于type是元类也就是类，因此它本身也是通过__new__方法生成其实例，只不过这个实例是一个类.
        return type.__new__(upperattr_metaclass, future_class_name, future_class_parents, uppercase_attr)
你可能已经注意到了有个额外的参数upperattr_metaclass，这并没有什么特别的。类方法的第一个参数总是表示当前的实例，就像在普通的类方法中的self参数一样。
当然了，为了清晰起见，这里的名字我起的比较长。但是就像self一样，所有的参数都有它们的传统名称。因此，在真实的产品代码中一个元类应该是像这样的：
class UpperAttrMetaclass(type):
    def __new__(cls, name, bases, dct):
        attrs = ((name, value) for name, value in dct.items() if not name.startswith('__')
        uppercase_attr  = dict((name.upper(), value) for name, value in attrs)
        return type.__new__(cls, name, bases, uppercase_attr)
如果使用super方法的话，我们还可以使它变得更清晰一些:
class UpperAttrMetaclass(type):
    def __new__(cls, name, bases, dct):
        attrs = ((name, value) for name, value in dct.items() if not name.startswith('__'))
        uppercase_attr = dict((name.upper(), value) for name, value in attrs)
        return super(UpperAttrMetaclass, cls).__new__(cls, name, bases, uppercase_attr)
'''


# 为Model构造ModelMetaclass，用来控制Model对象的创建，注意到Model只是一个基类，如何将具体的子类如User的映射信息读取出来呢？
# 答案就是通过metaclass：ModelMetaclass
class ModelMetaclass(type):
    # __new__控制__init__的执行，所以在其执行之前
    # cls:代表要__init__的类，此参数在实例化时由Python解释器自动提供(例如下文的User和Model)
    # bases：代表继承父类的集合
    # attrs：类的方法集合  
    def __new__(cls, name, bases, attrs):
        # 排除Model类本身：
        if name=='Model':
            return type.__new__(cls, name, bases, attrs) # 对Model类本身不做任何修改
        # 获取table名称：
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        # 获取所有的Field和主键名：
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items(): # attrs是一个dict，所以都是由Key：Value组成的，通过items()可以获取该dict所有的项
            if isinstance(v, Field): # 如果某个Key的Value是Field类型，说明找到了一组映射关系，将其存入mappings中
                logging.info(' found mapping: %s ==> %s' % (k, v))
                mappings[k] = v  # 里面存的是Field类型的对象和该对象的Key，一个Field对象对应着Mysql中table的一行
                if v.primary_key: # Field对象拥有primary_key属性，对应着Mysql中table的一列，标识对应行的数据(属性)是否是主键
                    # 找到主键：
                    if primaryKey: # 若已经存在主键了，则说明有了多余的主键
                        raise RuntimeError('Duplicate primary key for field: %s' % k) # 多余主键
                    primaryKey = k # 标识主键是哪个Key
                else: # 若不是主键，则将该属性存入fields列表中
                    fields.append(k)
        if not primaryKey: # 若是在所有的映射中都没有找到主键，则抛出没有找到主键的异常
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys(): # 迭代mappings中的所有key，针对所有找到的映射关系
            attrs.pop(k)  # attrs中的key就是类属性，将类属性移除，重新构建新的类属性，使定义的类字段不污染User类属性，只在实例中可以访问这些key
        # 保存除主键外的属性为''列表形式
        # 将除主键外的其他属性变成`id`, `name`这种形式
        # fields本来是一个存了非主键Key的列表(每个元素是一个Key的名称)，经过该语句之后，
        # 生成的escaped_fields也是一个列表，但是每个元素是一个map（一个map包含一个key和一个value），且该map的组成是('', fileds中存储的key)，
        # 这里的fields本来就是一个包含主键外属性的列表了（包含所有非主键的属性名称），再做这个处理有必要吗？
        escaped_fields = list(map(lambda f: '`%s`' % f, fields)) # f是lambda的参数，':'后面的计算结果是lambda的返回值，这里lambda返回一个f的值作为字符串的string
        # 重新构造attrs的属性：
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT，INSERT，UPDATE和DELETE语句：
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) value (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)  # 在__init__执行之前，将通过__new__重新构造的类返回
# 这样，任何继承自Model的类（比如User），会自动通过ModelMetaclass扫描映射关系，并存储到自身的类属性如__table__、__mappings__中
'''
1. ', '.join(escaped_fields)
    用','分割escaped_fields中的元素
2. ''中的%s会进一步的将%s展开成一个完成的string，而''中的`%s`只会直接将后面的%s的值放在这里
'''

'''
ORM

有了基本的select()和execute()函数，我们就可以开始编写一个简单的ORM了。
设计ORM需要从上层调用者角度来设计。先设计给最终使用提供的类Model，再设计修改Model属性的Meta类：ModelMetaclass
'''

'''
定义Model

首先要定义的是所有ORM映射的基类Model，指定metaclass，Model继承自dict，拥有字典的所有功能，同时实现特殊方法__getattr__和__setattr__,可以进行属性操作
实现数据库操作的所有方法，且定义为class方法，所有继承自Model的类（包括这些类的实例）都具有数据库操作方法
'''
class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw) # 通过__init__来init自己，可以忽略吗？

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None) #实际是调用了特殊方法__getsttr__，getattr()是默认的内置函数，会自动去调用__getattr__

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None: # 若属性key的值为空，则需要设置默认值
            field = self.__mappings__[key] # 这里的key是每个Field属性的key，也就是该key指定了现在这个value值对应的是Mysql中当前table的哪一个Field对象的当前值
            if field.default is not None: # 若对应Field中的default属性(列)不为空
                value = field.default() if callable(field.default) else field.default # filed.default有可能会是一个函数（去获取一个值来作为default值）
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    # 类方法有类变量cls传入，从而可以用cls做一些相关的处理。并且有子类继承时，调用该类方法时，传入的类变量cls是子类，而非父类。
    # 一般来说，要使用某个类的方法，需要先实例化一个对象再调用方法。
    # 而使用@staticmethod或@classmethod，就可以不需要实例化，直接类名.方法名()来调用。
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args) #返回的rs是一个元素是tuple的list
        return [cls(**r) for r in rs]  # 将select返回的rs(在Mysql中找到的数据)中的每一行数据(对应的类实例))组织成dict，再将所有的dict组织成一个列表List，通过cls返回给子类的对象
    
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s __num__ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['__num__']

    @classmethod
    async def find(cls, pk):
        ' find object by primary key. '
        #rs是一个list，里面是一个dict
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0]) #只返回rs中的第一个dict，也就是只返回第一个找到的Field实例，即找到的第一行数据

    # 往Model类添加实例方法，就可以让所有子类调用实例方法
    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__)) # 把非主键Filed实例与对应的当前value组成dict，并放在一个list中
        args.append(self.getValueOrDefault(self.__primary_key__)) # 在该list中加入主键对应的value
        rows = await execute(self.__insert__, args) # 调用__insert__，将该组Field值写如Mysql中
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

    async def update(self): # 该Field已存在，更新其对应的值
        args = list(map(self.getValue, self.__fields__)) # getValue得到的是对应table的某一行数据各列属性的当前值
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self): # 通过主键来删除某一个Field实例
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)




if __name__=='__main__': #一个类自带前后都有双下划线的方法，在子类继承该类的时候，这些方法会自动调用，比如__init__
    import sys
#    import pymysql
# 关于协程，@asyncio.coroutine 与 yield from 配对使用，前者标识一个函数是协程，后者在一个协程中调用另一个协程前使用
#          async 与 await 配对使用，前者标识一个函数是协程，后者在一个协程中调用另一个协程前使用
#     且 yield from 与 await 必须在一个协程中调用另一个协程时使用，不可在普通函数中使用(SyntaxError:'yield' inside function)
#     也不可在所有函数外使用（SyntaxError:'yield' outside function）

    Create_Database_test = '''
        CREATE DATABASE if not exists test  
    '''
    Create_table_user2 = '''
        CREATE TABLE if not exists user2(
            id BIGINT primary key not null, 
            name VARCHAR(20) not null, 
            email VARCHAR(35) not null, 
            password VARCHAR(32)
        )
    '''


    async def create_testdb_user2():
        connect = await aiomysql.connect(
            user = 'root',
            password = '0012344',
            host = '127.0.0.1',
            port = 3308,
            db = 'test',
            charset = 'utf8'
        )
        conn = await connect.cursor()
        await conn.execute(Create_Database_test)
        await conn.execute("use test")
        await conn.execute(Create_table_user2)
        await conn.close()
        connect.close()
# 关于 await conn.execute  await conn.close()  connect.close()，参考https://aiomysql.readthedocs.io/en/latest/
    

    # 创建一个table，table的名字为User2，该table包含4个字段
    class User2(Model): #虽然User类乍看没有参数传入，但实际上，User类继承Model类，Model类又继承dict类，所以User类的实例可以传入关键字参数，关键字参数就是dict参数
        __table__ = 'user2'
        id = IntegerField('id', primary_key=True) # 主键为id，tablename就是类名，就是User2
        name = StringField('name')
        email = StringField('email')
        password = StringField('password')

    # 创建异步loop事件句柄
    loop = asyncio.get_event_loop()

    # 创建任务实例
    async def test():
        await create_pool(loop=loop, host='localhost', port=3308, user='root', password='0012344', database='test')
#        user = User2(id=2, name='Tom', email='shibushi@gmail.com', password='12345')
#        await user.save()
        r = await User2.findAll() # 调用表User2的findAll方法，表示要在当前的表User2中查找所有数据
        print(r)

        await destroy_pool()

    tasks = [create_testdb_user2(),test()]

    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()
    if loop.is_closed():
        sys.exit(0)

