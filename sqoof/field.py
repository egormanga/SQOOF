import sqlalchemy
from graphene.types.unmountedtype import UnmountedType


class Field(sqlalchemy.Column):
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

		self.readable = readable
		self.writable = writable
		self.required = required
		self.create_only = create_only
		self.update_only = update_only
		self.read_permissions = frozenset(read_permissions)
		self.write_permissions = frozenset(write_permissions)

		if create_only and update_only:
			raise ValueError("Only one of `create_only` or `update_only` can be true.")

		if primary_key and self.updatable:
			raise ValueError("Primary keys cannot be updatable.")

		if not hasattr(self, '_type'):
			self._type = next(i for i in self.__class__.mro() if issubclass(i, UnmountedType))

		if sqltype := getattr(self, '_sqltype', None):
			if sqltype is sqlalchemy.dialects.postgresql.types.BYTEA:
				sqltype = sqltype(*args, length=kwargs.pop('length', None))
			else: sqltype = sqltype(*args)

			kwargs.pop('type_', None)
		elif sqltype := kwargs.pop('type_', None):
			sqltype = sqltype.__class__(*args)
		else:
			sqltype = None

		self.args = ()
		super().__init__(sqltype, primary_key=primary_key, nullable=(not required), **kwargs)

	@property
	def kwargs(self) -> dict:
		return {'required': self.required, **super().kwargs}

	@property
	def creatable(self) -> bool:
		return (self.writable and not self.update_only)

	@property
	def updatable(self) -> bool:
		return (self.writable and not self.create_only)
