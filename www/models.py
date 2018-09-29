#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Jassion Zhao'

'''
有了ORM，我们就可以把Web App需要的3个表用Model表示出来
'''

import time, uuid

from orm import Model, StringField, BooleanField, FloatField, TextField

def next_id(): # 以函数的形式自动生成id的默认值
    return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)

class User(Model):
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(default=time.time) # 用time.time（时间戳）作为created_at的默认值

class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(default=time.time)

class Comment(Model):
    __table__ = 'comments'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)

'''
在编写ORM时，给一个Field增加一个default参数可以让ORM自己填入缺省值，非常方便。并且，缺省值可以作为函数对象传入，在调用save()时自动计算。

例如，主键id的缺省值是函数next_id，创建时间created_at的缺省值是函数time.time，可以自动设置当前日期和时间。

日期和时间用float类型存储在数据库中，而不是datetime类型，这么做的好处是不必关心数据库的时区以及时区转换问题，排序非常简单，显示的时候，只需要做一个float到str的转换，也非常容易。
'''

'''
如果表的数量很少，可以手写创建表的SQL脚本, 如： sql_files/schema.sql
如果表的数量很多，可以从Model对象直接通过脚本自动生成SQL脚本，使用更简单。

把SQL脚本放到MySQL命令行里执行：

$ mysql -u root -p < schema.sql
我们就完成了数据库表的初始化。

命令行连接Mysql数据库：
>> mysql -P 端口号 -h mysql主机名或ip地址 -u 用户名 -p
例：
>> mysql -P 3306 -h 192.168.1.104 -u root -p
'''

if __name__ == '__main__':
    import orm, asyncio
    import sys

    loop = asyncio.get_event_loop()

    async def test():
        await orm.create_pool(loop=loop, user='www-data', password='www-data', database='db_web')
        user = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank') # 在users表中增加一项数据
        await user.save()
  
    tasks = [test()]
    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()

    if loop.is_closed():
        sys.exit(0)

# 可以登录Mysql，查看到db_web.users表中已经存在该项数据了

