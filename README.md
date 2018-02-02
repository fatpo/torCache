# torCache
基于tornado的双缓存机制，轻松帮你单实例支持并发200qps+.   
需要解决两个问题：    
1、为什么需要缓存？     
2、在tornado框架怎么pythonic得添加缓存？    

回答1：    
比如获取文章，假设某公司的运营，每周只更新3次文章，但是GetArticle接口每一次都去数据库获取文章列表，这是不明智的, 所以需要缓存.      

回答2：    
最好是有个装饰器，然后一挂上去就能自动满足逻辑条件，类似flask的login等装饰器...   


# 项目背景
tornado==4.2   
tormysql==0.2.9    
采用protobuf作为通信协议.    

# 双缓存之DAO缓存
```
def dao_cache_wrapper(key, expire_seconds=DAO_CACHE_TIME):
    """
    缓存装饰器，加之，就能自动来一套获取缓存，若缓存不存在则自动添加缓存...
    :param key: 缓存的key
    :param expire_seconds: 超时时间，秒
    :return:
    """

    def wrapper(func):
        @tornado.gen.coroutine
        def new_func(*args, **kwargs):
            complate_key = key

            # 以下是根据不同的业务要求定制缓存的key，如
            if 'student' in key and 'student_id' in kwargs:
                complate_key = complate_key % str(kwargs['student_id'])

            # 以下是配置中大概率会带的参数：page
            if 'page' in kwargs:
                complate_key = complate_key + str(kwargs['page'])

            logging.info(">>>>> cache final key =%s" % complate_key)

            item = mycache.get(complate_key)
            if item:
                raise tornado.gen.Return(item)

            item = yield func(*args, **kwargs)
            if item:
                logging.info("set cache, key=%s" % complate_key)
                mycache.set(complate_key, item, expire_seconds)

            raise tornado.gen.Return(item)

        return new_func

    return wrapper
```

# 双缓存之Handler缓存
```
def handler_cache_wrapper(key, expire_seconds=HANDLER_CACHE_TIME):
    """
    处理器的缓存修饰器
    因为本项目是采用protobuf去实现，所以定制缓存的时候，比json要麻烦些许...

    若缓存存在，则直接返回...
    若缓存不存在，则真正进入业务处理逻辑，处理后增加缓存...
    :param key: 缓存key
    :param expire_seconds: 过期时间，秒
    :return:
    """

    def inner_wrapper(func):
        @tornado.gen.coroutine
        def new_func(*args, **kwargs):
            complate_key = key

            my_instance = args[0]
            context = my_instance.context
            pool = my_instance.pools
            req_info = my_instance.req_info
            rsp_info = my_instance.rsp_info

            if req_info.req:
                # 先把pb对象解析成json，为了拿到里面的参数，比如page、user_id 之类的...
                # 再将这些参数归并到complate_key， 组成一个完整的缓存key，如：cmd_GetUserProfileHandler_user_id_1000185301
                req_dict = protobuf_json.pb2json(req_info.req)
                for req_key, req_value in req_dict.iteritems():
                    complate_key = complate_key + '_%s_%s' % (req_key, req_value)

            # 控制某些用户不走缓存通道，比如白名单用户...
            user_id = context.sid_info.userid
            if int(user_id) in RECOMMEND_WHITE_LIST:
                logging.info("用户=%s,在白名单[%s]中，不走缓存通道..." % user_id)
                yield func(*args, **kwargs)
                return

            # 因为user_id不是带在pb中的请求对象中，而是根据token算出来的，所以加上id
            # 一般这种接口都是个性化接口如：cmd_GetUser，那么此时需要在传入基础key=cmd_GetUser_user，那么会补充为key=cmd_GetUser_user_10003
            if 'user' in key:
                complate_key = complate_key + '_%s' % user_id

            # 其他的开启缓存之旅...
            rsp_item = mycache.get(complate_key, pb_value=True)
            if rsp_item:
                logging.info("Get from cache, key=%s" % complate_key)
                rsp_info.rsp.ParseFromString(rsp_item)
                return

            # 真正处理逻辑
            ret = yield func(*args, **kwargs)

            # 只有在成功的情况下，才建立缓存...
            if ret:
                logging.info("set cache, key=%s" % complate_key)
                mycache.set(complate_key, rsp_info.rsp.SerializeToString(), expire_seconds=expire_seconds,
                            pb_value=True)

        return new_func

    return inner_wrapper

```

# 测试用例-1
```
# coding=utf-8
import logging

import tornado.gen

from Base import BizBaseHandler
from cache import handler_cache_wrapper
from dao.Student import StudentDao


class GetStudentHandler(BizBaseHandler):
    """
        处理获取学生 list请求
        假设大家都有一个业务处理逻辑，并用类包装起来，真正的处理是run()...
    """

    def __init__(self, context, pools, req_info, rsp_info):
        super(GetStudentHandler, self).__init__(context, pools, req_info, rsp_info)

    @handler_cache_wrapper(key="cmd_GetStudentHandler")
    @tornado.gen.coroutine
    def run(self):
        page = self.req_info.req.page
        type_id = self.req_info.req.type_id
        logging.info("page=%s, type=%s" % (page, type_id))

        try:
            # 先获取禅在app的文章运营列表
            pool = self.pools[0]
            with (yield pool.Connection()) as conn:
                yield conn.commit()

                std_infos = yield StudentDao.get_all(self.context, conn, page)

                logging.info("student len=%s" % len(std_infos))
                for std_info in std_infos:
                    pb_student = self.rsp_info.rsp.student.add()
                    pb_student.id = std_info.id
                    pb_student.name = std_info.name
                    pb_student.age = std_info.age

            raise tornado.gen.Return(True)
        except tornado.gen.Return:
            raise
        except Exception, ex:
            logging.error(ex, exc_info=1)
            raise tornado.gen.Return(False)

```

# 测试用例-2
```
# coding=utf-8
import tornado.gen

from Base import BaseDao
from cache import dao_cache_wrapper
from info.Student import StudentInfo


class StudentDao(BaseDao):
    DataInfo = StudentInfo
    table_name = 'student'  # table name
    escape_list = ['name']  # the list need to be escaped
    quot_list = ['create_time', 'update_time']  # the list requires quoted
    not_append_list = ['del_flag']  # int list like: img_id
    append_list = ['age']  # int list, but sometimes need to += n, like: add_cnt = add_cnt+10, view_cnt=view_cnt+1

    @classmethod
    @dao_cache_wrapper(key="student_user")
    @tornado.gen.coroutine
    def get_std_by_id(cls, context, conn, std_id):
        """
        根据id 获取学生
        :param context: 请求上下文
        :param conn: 连接
        :param std_id: 学生id
        :return: StudentInfo or None
        """
        with conn.cursor() as cursor:
            sql = "select * from %s where del_flag=0 and id=%s" % (cls.table_name, std_id)
            yield cursor.execute(sql)
            item = cursor.fetchone()
            if not item:
                raise tornado.gen.Return(None)
            info = cls.DataInfo(item)
            raise tornado.gen.Return(info)

```
