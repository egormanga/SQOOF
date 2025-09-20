from sqlalchemy.dialects.postgresql.types import BYTEA as BitVar
from sqlalchemy.types import (
	BigInteger as BigInt,
	DECIMAL as Decimal,
	Integer as Int,
	JSON as JSONString,
	Numeric as Float,
	SmallInteger as SmallInt,
)
for k, v in globals().copy().items():  # monkey patching
	if isinstance(v, type) and 'sqlalchemy' in v.__module__:
		v.__name__ = k

import graphene.types
import sqlalchemy.types

from . import Field as _Field


globals().update({
	column_type.__name__: type(
		column_type.__name__,
		(_Field, graphene_type),
		{'_type': graphene_type, '_sqltype': column_type, '__doc__': graphene_type.__doc__},
	)
	for column_type, graphene_type in {
		BigInt: graphene.types.BigInt,
		BitVar: graphene.types.String,
		Decimal: graphene.types.Decimal,
		Float: graphene.types.Float,
		Int: graphene.types.Int,
		SmallInt: graphene.types.Int,
		sqlalchemy.types.Date: graphene.types.Date,
		sqlalchemy.types.DateTime: graphene.types.DateTime,
		sqlalchemy.types.String: graphene.types.String,
		sqlalchemy.types.Uuid: graphene.types.UUID,
	}.items()
})
