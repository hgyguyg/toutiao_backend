from fastapi import HTTPException

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from utils.exception import http_exception_handler, integrity_error_handler,sqlalchemy_error_handler,general_exception_handler


def register_exception_handler(app:FastAPI):
    app.add_exception_handler(HTTPException,http_exception_handler) #业务错误
    app.add_exception_handler(IntegrityError,integrity_error_handler) #数据完整性错误
    app.add_exception_handler(SQLAlchemyError,sqlalchemy_error_handler) #数据库错误
    app.add_exception_handler(Exception,general_exception_handler) #其他错误

