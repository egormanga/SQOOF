from typing import Iterator


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


# by Sdore, 2023-26
#   www.sdore.me
