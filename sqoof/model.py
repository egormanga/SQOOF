import datetime
import enum

import graphene
import sqlalchemy.orm
from sqlalchemy import delete, insert, not_, or_, select, type_coerce, update

from .field import Field
from .types import String
from .utils import classproperty


class FiltersMeta(graphene.utils.subclass_with_meta.SubclassWithMeta_Meta):
	def __new__(metacls, name, bases, classdict):
		classdict['or'] = classdict['not'] = graphene.InputField(graphene.List(graphene.NonNull(lambda: cls)))
		cls = super().__new__(metacls, name, bases, classdict)
		return cls


class Filters(graphene.InputObjectType, metaclass=FiltersMeta):
	pass


class Filter(graphene.InputObjectType):
	pass


class ModelMeta(sqlalchemy.orm.decl_api.DeclarativeAttributeIntercept, graphene.types.objecttype.ObjectTypeMeta):
	def __new__(metacls, name, bases, classdict):
		fields = classdict['_fields'] = {k: v for c in (*tuple(i.__dict__ for i in bases), classdict) for k, v in c.items() if isinstance(v, Field)}

		classdict['Filters'] = type(
			f"{name}Filters",
			(Filters,),
			{k: type(f"{name}Filter_{k}", (Filter,), {
				'eq': t(*v.args),
				'ne': t(*v.args),
				'lt': t(*v.args),
				'gt': t(*v.args),
				'le': t(*v.args),
				'ge': t(*v.args),
				'in': graphene.List(graphene.NonNull(t, *v.args)),
				'notin': graphene.List(graphene.NonNull(t, *v.args)),
				'contains': t(*v.args),
			})() for k, v in fields.items() if v.readable and (t := (v._type if not isinstance(v, String) else graphene.types.String))},
		)

		if any(i.readable for i in fields.values()):
			classdict['Type'] = type(
				name,
				(graphene.ObjectType,),
				{
					'__doc__': (classdict['__doc__'].strip() if classdict.get('__doc__') else None),
					**{k: (v if not isinstance(v, String) else graphene.types.String(*v.args)) for k, v in fields.items() if v.readable},
				},
			)

		if any(i.readable for i in fields.values()):
			classdict['Read'] = type(
				f"Read{name}Input",
				(graphene.InputObjectType,),
				{
					'__doc__': (classdict['__doc__'].strip() if classdict.get('__doc__') else None),
				},
			)

		if any(i.creatable for i in fields.values()):
			classdict['Create'] = type(
				f"Create{name}Input",
				(graphene.InputObjectType,),
				{
					'__doc__': (classdict['__doc__'].strip() if classdict.get('__doc__') else None),
					**{k: (v if not isinstance(v, String) else graphene.types.String(*v.args)) for k, v in fields.items() if v.creatable},
				},
			)

		if any(i.updatable for i in fields.values()):
			classdict['Update'] = type(
				f"Update{name}Input",
				(graphene.InputObjectType,),
				{
					'__doc__': (classdict['__doc__'].strip() if classdict.get('__doc__') else None),
					**{k: (v._type if not isinstance(v, String) else graphene.types.String)(*v.args) for k, v in fields.items() if v.updatable},
				},
			)

		return super().__new__(metacls, name, bases, classdict)


class Model(metaclass=ModelMeta):
	read_permissions: frozenset[str] = frozenset({'any'})
	create_permissions: frozenset[str] = frozenset({'any'})
	update_permissions: frozenset[str] = frozenset({'any'})
	delete_permissions: frozenset[str] = frozenset({'any'})

	@classproperty
	def primary_key(cls):
		return {k: v for k, v in cls._fields.items() if v.primary_key is True}

	@staticmethod
	def _compile_filter(field, filter: Filter):
		if isinstance(filter, dict):
			for k, v in filter.items():
				match k:
					case 'eq': yield (field == v)
					case 'ne': yield (field != v)
					case 'lt': yield (field <  v)
					case 'gt': yield (field >  v)
					case 'le': yield (field <= v)
					case 'ge': yield (field >= v)
					case 'in': yield (field in v)
					case 'notin': yield (field not in v)
					case 'contains': yield (v in field)
					case _: raise ValueError(f"Unknown filter: {k}")
		elif isinstance(filter, list): return ((field in filter),)
		else: return ((field == filter),)

	@classmethod
	def _compile_filters(cls, filters: Filters):
		for k, v in filters.items():
			match k:
				case 'or': yield or_(*map(cls._compile_filters, v))
				case 'not': yield not_(or_(*map(cls._compile_filters, v)))
				case _: yield from cls._compile_filter(getattr(cls, k), v)

	@classmethod
	def _resolve_enums(cls, d) -> dict:
		return {k: (type_coerce(v.value, None) if isinstance(v, enum.Enum) else cls._resolve_enums(v) if isinstance(v, dict) else v) for k, v in d.items()}

	@classmethod
	async def resolve(cls, context, info, *, id):
		query = select(cls).where(cls.id == id)

		async with info.context['request'].state.db.connect() as conn:
			return (await conn.execute(query)).fetchone()

	@classmethod
	async def resolve_list(cls, context, info, *, filters: Filters = None):
		filters = (cls._resolve_enums(filters) if filters is not None else {})

		query = select(cls)

		if filters:
			query = query.where(*cls._compile_filters(filters))

		async with info.context['request'].state.db.connect() as conn:
			return (await conn.execute(query)).fetchall()

	@classmethod
	async def resolve_create(cls, context, info, *, input=None):
		input = (cls._resolve_enums(input) if input is not None else {})

		now = datetime.datetime.now()
		input.update({
			'created': now,
			'updated': now,
		})

		query = insert(cls).values(**input).returning(cls)

		async with info.context['request'].state.db.begin() as conn:
			return (await conn.execute(query)).fetchone()

	@classmethod
	async def resolve_update(cls, context, info, *, id, input=None):
		# TODO:
		# 1. написать маппинг update
		# 2. написать фильтры для where(…)
		input = (cls._resolve_enums(input) if input is not None else {})

		now = datetime.datetime.now()
		input.update({
			'updated': now,
		})

		query = update(cls).where(cls.id == id).values(**input).returning(cls)

		async with info.context['request'].state.db.begin() as conn:
			return (await conn.execute(query)).fetchone()

	@classmethod
	async def resolve_update_list(cls, context, info, *, filters: Filters, input=None):
		filters = cls._resolve_enums(filters)
		input = (cls._resolve_enums(input) if input is not None else {})

		now = datetime.datetime.now()
		input.update({
			'updated': now,
		})

		query = update(cls).where(*cls._compile_filters(filters)).values(**input).returning(cls)

		async with info.context['request'].state.db.begin() as conn:
			return (await conn.execute(query)).fetchall()

	@classmethod
	async def resolve_delete(cls, context, info, *, id):
		query = delete(cls).where(cls.id == id)

		async with info.context['request'].state.db.begin() as conn:
			await conn.execute(query) # TODO: return

	@classmethod
	async def resolve_delete_list(cls, context, info, *, filters: Filters):
		filters = cls._resolve_enums(filters)

		query = delete(cls).where(*cls._compile_filters(filters))

		async with info.context['request'].state.db.begin() as conn:
			await conn.execute(query) # TODO: return
