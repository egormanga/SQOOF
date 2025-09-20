from typing import Any, Iterator


def to_camel_case(text: str) -> str:
	return str().join((i.title() if ii == 1 else i) for ii, i in enumerate(text.split('_')))


def keys_to_camel(d: dict[str, Any]) -> dict[str, Any]:
	return {to_camel_case(k): v for k, v in d.items()}


def allsubclasses(c: type) -> Iterator[type]:
	for i in c.__subclasses__():
		yield i
		yield from allsubclasses(i)


class classproperty:
	__slots__ = ('__wrapped__',)

	def __init__(self, f):
		self.__wrapped__ = f

	def __get__(self, obj, cls):
		return self.__wrapped__(cls)
