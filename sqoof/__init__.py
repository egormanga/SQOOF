#!/usr/bin/env python3
# Structured Querying in Object Oriented Fashion

import graphene

from .field import Field
from .model import Model
from .utils import allsubclasses


def generate_query(base: type) -> type:
	return type(
		'Query',
		(graphene.ObjectType,),
		{k: v for model in allsubclasses(base) for k, v in {
			f"{model.__name__[0].lower()}{model.__name__[1:]}": graphene.Field(
				model.Type,
				args=model.primary_key,
				required=False,
				resolver=model.resolve,
			),
			f"{model.__name__[0].lower()}{model.__name__[1:]}s": graphene.List(
				graphene.NonNull(model.Type),
				args={'filters': model.Filters()},
				required=False,
				resolver=model.resolve_list,
			),
		}.items()},
	)

def generate_mutation(base: type) -> type:
	return type(
		'Mutation',
		(graphene.ObjectType,),
		{k: v for model in allsubclasses(base) for k, v in {
			f"create{model.__name__}": graphene.Field(
				model.Type,
				args=({'input': model.Create(required=True)} if hasattr(model, 'Create') else None),
				required=True,
				resolver=model.resolve_create,
			),

			**({
				f"update{model.__name__}": graphene.Field(
					model.Type,
					args={
						**model.primary_key,
						'input': model.Update(required=True),
					},
					required=True,
					resolver=model.resolve_update,
				),
				f"update{model.__name__}s": graphene.List(
					graphene.NonNull(model.Type),
					args={
						'filters': model.Filters(required=True),
						'input': model.Update(required=True),
					},
					resolver=model.resolve_update_list,
				),
			} if hasattr(model, 'Update') else {}),

			f"delete{model.__name__}": graphene.Field(
				model.Type,
				args=model.primary_key,
				resolver=model.resolve_delete,
			),
			f"delete{model.__name__}s": graphene.List(
				graphene.NonNull(model.Type),
				args={'filters': model.Filters(required=True)},
				required=False,
				resolver=model.resolve_delete_list,
			),
		}.items() if v.args is not None},
	)


# by Sdore, 2023-25
#   www.sdore.me
