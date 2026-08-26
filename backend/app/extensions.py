"""全局扩展对象，避免循环依赖。"""
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

db = SQLAlchemy()
cors = CORS()
