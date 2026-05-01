import enum

import graphene
import sqlalchemy.orm
from sqlalchemy import and_, delete, insert, not_, or_, select, type_coerce, update
from sqlalchemy.ext.asyncio import AsyncSession

from .field import Field, RelationField
from .types import String
from .utils import classproperty


class FiltersMeta(graphene.InputObjectType.__class__):
	def __new__(metacls, name, bases, classdict):
		classdict['and'] = classdict['or'] = classdict['not'] = graphene.InputField(graphene.List(graphene.NonNull(lambda: cls)))
		cls = super().__new__(metacls, name, bases, classdict)
		return cls


class Filters(graphene.InputObjectType, metaclass=FiltersMeta):
	pass


class Filter(graphene.InputObjectType):
	pass


class ModelMeta(sqlalchemy.orm.DeclarativeBase.__class__, graphene.ObjectType.__class__):
	def __new__(metacls, name, bases, classdict):
		fields = classdict['_fields'] = {k: v
		                                 for c in (*(i.__dict__ for i in bases), classdict)
		                                 for k, v in c.items()
		                                 if isinstance(v, Field)}

		classdict['Type'] = type(name, (graphene.ObjectType,), {
			'__doc__': (doc := (classdict['__doc__'].strip() if classdict.get('__doc__') else None)),
			**{k: (v if not isinstance(v, String) else graphene.types.String(*v.args))
			   for k, v in fields.items()
			   if v.readable},
		})

		classdict['Filters'] = type(f"{name}Filters", (Filters,), {
			k: type(f"{name}Filter_{k}", (Filter,), {
				**{op.__name__.removesuffix('_op').replace('not_', 'not'): v._type(*v.args)
				   for op in sqlalchemy.sql.operators._comparison
				   if op not in (
				   	sqlalchemy.sql.operators.is_,
				   	sqlalchemy.sql.operators.is_not,
				   	sqlalchemy.sql.operators.function_as_comparison_op,
				   )},
				'in': graphene.List(v._type, *v.args),
				'notin': graphene.List(v._type, *v.args),
			})()
			for k, v in fields.items()
			if v.filterable
		})

		if any(i.creatable for i in fields.values()):
			classdict['Create'] = type(f"Create{name}Input", (graphene.InputObjectType,), {
				'__doc__': doc,
				**{k: v for k, v in fields.items() if v.creatable},
			})

		if any(i.updatable for i in fields.values()):
			classdict['Update'] = type(f"Update{name}Input", (graphene.InputObjectType,), {
				'__doc__': doc,
				**{k: (v._type if not isinstance(v, String) else graphene.types.String)(*v.args)
				   for k, v in fields.items()
				   if v.updatable},
			})

		return super().__new__(metacls, name, bases, classdict)


class Model(metaclass=ModelMeta):
	read_permissions: frozenset[str] = frozenset({'any'})
	create_permissions: frozenset[str] = frozenset({'any'})
	update_permissions: frozenset[str] = frozenset({'any'})
	delete_permissions: frozenset[str] = frozenset({'any'})

	@classproperty
	def primary_key(cls):
		return (i for i in cls.__dict__.values() if isinstance(i, sqlalchemy.orm.Mapped) and getattr(i, 'primary_key', None) is True)

	@classproperty
	def primary_keys(cls):
		return {k: v for k, v in cls._fields.items() if v.primary_key is True}

	@staticmethod
	def _compile_filter(field, filter: Filter):
		for k, v in filter.items():
			match k:
				case 'ne': yield ((field.is_(None) | (field != v)) if v is not None else field.is_not(v))
				case 'in': yield ((field.is_(None) | field.in_(i for i in v if i is not None)) if None in v else field.in_(v))
				case 'notin': yield ((field.is_not(None) & field.notin_(i for i in v if i is not None)) if None in v else (field.is_(None) | field.notin_(v)))
				case _:
					for k_ in (k, k+'_', k+'_op'):
						if sqlalchemy.sql.operators.is_comparison(op := getattr(sqlalchemy.sql.operators, k_, None)):
							yield op(field, v)
							break
					else: raise ValueError(f"Unknown filter: {k}")

	@classmethod
	def _compile_filters(cls, filters: Filters):
		for k, v in filters.items():
			match k:
				case 'and': yield and_(*(j for i in map(cls._compile_filters, v) for j in i))
				case 'or': yield or_(*(j for i in map(cls._compile_filters, v) for j in i))
				case 'not': yield not_(or_(*(j for i in map(cls._compile_filters, v) for j in i)))
				case _: yield from cls._compile_filter(getattr(cls, k), v)

	@classmethod
	def _resolve_enums(cls, d) -> dict:
		return {k: (type_coerce(v.value, None) if isinstance(v, enum.Enum) else cls._resolve_enums(v) if isinstance(v, dict) else v) for k, v in d.items()}

	@classmethod
	def _parse_selection(cls, nodes) -> dict:
		return {i.name.value: (cls._parse_selection(i.selection_set.selections) if i.selection_set is not None else {}) for i in nodes}

	@staticmethod
	def _parse_strategy(f):
		match f.prop.lazy:
			case None | 'noload': return sqlalchemy.orm.noload(f)
			case True | 'select': return sqlalchemy.orm.lazyload(f)
			case False: return sqlalchemy.orm.joinedload(f)
			case 'dynamic': return sqlalchemy.orm.dynamic_loader(f)
			case 'raise_on_sql': return sqlalchemy.orm.raiseload(f, sql_only=True)
			case _: return getattr(sqlalchemy.orm, f"{f.prop.lazy}load")(f)

	@classmethod
	def _resolve_selection(cls, fields, *, load: sqlalchemy.orm.Load = None) -> list:
		if load is None: load = sqlalchemy.orm.Load(cls)
		res = list()
		for k, v in fields.items():
			if isinstance((f := getattr(cls, k)).prop, RelationField):
				load = load.options(f.prop._type._resolve_selection(v, load=cls._parse_strategy(f)))
			else: res.append(f)
		return load.load_only(*res).raiseload('*')

	@classmethod
	async def resolve(cls, context, info, *, id):
		query = select(cls).where(cls.id == id)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db) as sess:
			return (await sess.execute(query)).scalar_one_or_none()

	@classmethod
	async def resolve_list(cls, context, info, *, filters: list[Filters] = None) -> list:
		query = select(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		if filters := (list(map(cls._resolve_enums, filters)) if filters is not None else ()):
			query = query.where(*(j for i in map(cls._compile_filters, filters) for j in i))

		async with AsyncSession(info.context['request'].state.db) as sess:
			return (await sess.scalars(query)).all()

	@classmethod
	async def resolve_create(cls, context, info, *, input):
		input = cls._resolve_enums(input)

		query = insert(cls).values(**input).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.execute(query)).scalar_one()

	@classmethod
	async def resolve_create_list(cls, context, info, *, input: list) -> list:
		input = list(map(cls._resolve_enums, input))

		query = insert(cls).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.scalars(query, input)).all()

	@classmethod
	async def resolve_update(cls, context, info, *, id, input):
		input = cls._resolve_enums(input)

		query = update(cls).where(cls.id == id).values(**input).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.execute(query)).scalar_one_or_none()

	@classmethod
	async def resolve_update_list(cls, context, info, *, filters: list[Filters], input) -> list:
		filters = list(map(cls._resolve_enums, filters))
		input = cls._resolve_enums(input)

		query = update(cls).where(*(j for i in map(cls._compile_filters, filters) for j in i)).values(**input).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.scalars(query)).all()

	@classmethod
	async def resolve_delete(cls, context, info, *, id):
		query = delete(cls).where(cls.id == id).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.execute(query)).scalar_one_or_none()

	@classmethod
	async def resolve_delete_list(cls, context, info, *, filters: list[Filters]) -> list:
		filters = list(map(cls._resolve_enums, filters))

		query = delete(cls).where(*(j for i in map(cls._compile_filters, filters) for j in i)).returning(cls)

		if fields := cls._parse_selection(info.field_nodes):
			query = query.options(cls._resolve_selection(fields[info.field_name]))

		async with AsyncSession(info.context['request'].state.db, expire_on_commit=False) as sess:
			async with sess.begin():
				return (await sess.scalars(query)).all()


# by Sdore, 2023-26
#   www.sdore.me
