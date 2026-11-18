from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.model import Model


class BaseModel(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


db = SQLAlchemy(model_class=BaseModel)
