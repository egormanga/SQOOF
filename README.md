# Structured Querying in Object Oriented Fashion
###### (p.k.a. GQLAlchemy _(not [that one](https://github.com/memgraph/gqlalchemy))_ or The Magic™)

## Example:
```py
import contextlib
import os

import graphene
import sqlalchemy.orm
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette
from starlette_graphene3 import GraphQLApp, make_playground_handler

from sqoof import Field, Model, generate_mutation, generate_query
from sqoof.types import *


PERMISSIONS = (
	ALL := 'all',
	SELF := 'self',
	SUPPORT := 'support',
	ADMIN := 'admin',
)


class Status(Field, graphene.Enum):
	active = 'active'
	disabled = 'disabled'
	deleted = 'deleted'
	banned = 'banned'


class Base(sqlalchemy.orm.DeclarativeBase):
	pass


class BaseModel(Model):
	id = Uuid(primary_key=True, required=True, server_default='gen_random_uuid()')
	status = Status(writable=True, required=True, update_only=True)


class User(Base, BaseModel):
	__tablename__ = 'user'

	first_name = String(127, writable=True)
	last_name = String(127, writable=True)

	create_permissions = {ADMIN}
	read_permissions = {SELF, SUPPORT, ADMIN}
	update_permissions = {SELF, SUPPORT, ADMIN}


class Query(generate_query(Base)):
	pass


class Mutation(generate_mutation(Base)):
	pass


schema = graphene.Schema(query=Query, mutation=Mutation, auto_camelcase=True)

db = create_async_engine(os.getenv('DB_DSN'))


@contextlib.asynccontextmanager
async def lifespan(app):
	yield {'db': db}


app = Starlette(lifespan=lifespan)
app.mount('/', GraphQLApp(schema, on_get=make_playground_handler()))
```
