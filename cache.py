# coding=utf-8
import cPickle as pickle
import logging

import redis
import tornado.gen

from tools import protobuf_json

# 这里可以是redis instance 或者 memcache instance
cache_client = redis.Redis(host='localhost', port=6379, db=1, password="yourpass")

# 是否打开缓存开关
cache_flag = True

# 超时时间
HANDLER_CACHE_TIME = 600  # 10分钟
DAO_CACHE_TIME = 600  # 10分钟

# 白名单用户，不走缓存通道
RECOMMEND_WHITE_LIST = [10001, 10002]


class MyCache(object):
    def __init__(self):
        pass

    @staticmethod
    def get(name, pb_value=False):
        if not cache_flag:
            return None

        value = cache_client.get(name)
        if not value:
            return None

        if not pb_value:
            value = pickle.loads(value)
        return value

    @staticmethod
    def set(name, value, expire_seconds=None, pb_value=False):
        if not cache_flag:
            return

        if not pb_value:
            value = pickle.dumps(value)

        if not expire_seconds:
            cache_client.set(name, value)
        else:
            cache_client.set(name, value, ex=expire_seconds)

    @staticmethod
    def backend_delete(key):
        cache_client.delete(key)

    @staticmethod
    def backend_get_keys(key):
        keys = cache_client.keys(key)
        return keys


def dao_cache_wrapper(key, expire_seconds=DAO_CACHE_TIME):
    """
    缓存装饰器，加之，就能自动来一套获取缓存，若缓存不存在则自动添加缓存...
    
    经查阅文档，redis的key长度无限制,value<=512MB即可，所以我们拼装起来的key理论上不会触发长度限制问题。
    1、这是一个策略问题，太短不方便管理、查阅，太长会增加计算成本，个人偏向前者.
    2、此处的key是有req中的请求参数拼装，理论上是长度有限，不会造成太大的困扰，固不考虑之...
    
    :param key: 缓存的key
    :param expire_seconds: 超时时间，秒
    :return:
    """

    def wrapper(func):
        @tornado.gen.coroutine
        def new_func(*args, **kwargs):
            complate_key = key

            # 以下是根据不同的业务要求定制缓存的key，如
            if 'temple_fahui_tag' in key and 'zzh_tag_id' in kwargs:
                complate_key = complate_key % str(kwargs['zzh_tag_id'])

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


mycache = MyCache()
print mycache
