# coding=utf-8


class BizBaseHandler(object):
    """
        业务逻辑基础handlers
    """

    def __init__(self, context, pools, req_info, rsp_info):
        """
        业务逻辑 - Base处理器
        :param context: 上下文context = ProtocolInfo，解析层解析后的obj实例
        :param pools: 数据库连接池
        :param req_info: 解析层ReqInfo的一个实例
        :param rsp_info: 解析层RspInfo的一个实例
        :return:
        """
        self.context = context
        self.pools = pools
        self.req_info = req_info
        self.rsp_info = rsp_info
