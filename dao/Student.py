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
