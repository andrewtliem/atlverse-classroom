from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base) 