# coding=utf-8
import logging

import tornado.gen

from Base import BizBaseHandler
from cache import handler_cache_wrapper
from dao.Student import StudentDao


class GetStudentHandler(BizBaseHandler):
    """
        处理获取学生 list请求
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
