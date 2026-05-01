import graphene
import sqlalchemy.orm
from graphene.types.unmountedtype import UnmountedType


class Field:
	readable: bool
	writable: bool
	required: bool
	create_only: bool
	update_only: bool
	read_permissions: frozenset[str]
	write_permissions: frozenset[str]

	def __init__(
		self,
		*args,
		primary_key: bool = False,
		readable: bool = True,
		writable: bool = False,
		required: bool = False,
		create_only: bool = False,
		update_only: bool = False,
		read_permissions: set[str] = frozenset({'all'}),
		write_permissions: set[str] = frozenset({'all'}),
		**kwargs
	):
		if primary_key: required = True
		if kwargs.pop('nullable', None): required = True

		self.readable = readable
		self.writable = writable
		self.required = required
		self.create_only = create_only
		self.update_only = update_only
		self.read_permissions = frozenset(read_permissions)
		self.write_permissions = frozenset(write_permissions)

		if create_only and update_only:
			raise ValueError("Only one of `create_only` or `update_only` can be true.")

		if self.creatable and not writable:
			raise ValueError("Creatable fields must be writable.")

		if self.updatable and not writable:
			raise ValueError("Updatable fields must be writable.")

		if primary_key and self.updatable:
			raise ValueError("Primary keys cannot be updatable.")

		if not hasattr(self, '_type'):
			self._type = next(i for i in self.__class__.mro() if issubclass(i, UnmountedType))

		if sqltype := getattr(self, '_sqltype', None):
			if len(args) <= 1 or not isinstance(args[1], sqltype):
				if sqltype is sqlalchemy.dialects.postgresql.types.BYTEA:
					args = (sqltype(*args, length=kwargs.pop('length', None)),)
				else: args = (sqltype(*args),)

			kwargs.pop('type_', None)
		elif sqltype := kwargs.pop('type_', None):
			args = (sqltype.__class__(*args),)

		self.args = ()
		super().__init__(*args, *kwargs.pop('args', ()), primary_key=primary_key, nullable=(not required), **kwargs)

	@property
	def kwargs(self) -> dict:
		return {'required': self.required, **super().kwargs}

	@property
	def creatable(self) -> bool:
		return (self.writable and not self.update_only)

	@property
	def updatable(self) -> bool:
		return (self.writable and not self.create_only)

	@property
	def filterable(self) -> bool:
		return self.readable

class ColumnField(Field, sqlalchemy.Column): pass

class EnumField(ColumnField, graphene.Enum): pass


class _BareField:
	def __init__(self, *args, primary_key=None, nullable=None, **kwargs):
		self.primary_key, self.nullable = primary_key, nullable
		super().__init__(*args, **kwargs)

class RelationField(Field, _BareField, sqlalchemy.orm.Relationship):
	filterable = False

	@property
	def _type(self) -> type:
		try: return self.mapper.class_
		except AttributeError: return None


# by Sdore, 2025-26
#   www.sdore.me
