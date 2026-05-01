#!/usr/bin/env python3
# Structured Querying in Object-Oriented Fashion

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
				args=model.primary_keys,
				resolver=model.resolve,
			),
			f"{model.__name__[0].lower()}{model.__name__[1:]}s": graphene.List(
				graphene.NonNull(model.Type),
				args={'filters': graphene.List(graphene.NonNull(model.Filters))},
				resolver=model.resolve_list,
				required=True,
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
				resolver=model.resolve_create,
				required=True,
			),
			f"create{model.__name__}s": graphene.Field(
				graphene.List(graphene.NonNull(model.Type), required=True),
				args=({'input': graphene.List(graphene.NonNull(model.Create), required=True)} if hasattr(model, 'Create') else None),
				resolver=model.resolve_create_list,
				required=True,
			),

			**({
				f"update{model.__name__}": graphene.Field(
					model.Type,
					args={
						**model.primary_keys,
						'input': model.Update(required=True),
					},
					resolver=model.resolve_update,
				),
				f"update{model.__name__}s": graphene.List(
					graphene.NonNull(model.Type),
					args={
						'filters': graphene.List(graphene.NonNull(model.Filters), required=True),
						'input': model.Update(required=True),
					},
					resolver=model.resolve_update_list,
					required=True,
				),
			} if hasattr(model, 'Update') else {}),

			f"delete{model.__name__}": graphene.Field(
				model.Type,
				args=model.primary_keys,
				resolver=model.resolve_delete,
			),
			f"delete{model.__name__}s": graphene.List(
				graphene.NonNull(model.Type),
				args={'filters': graphene.List(graphene.NonNull(model.Filters), required=True)},
				resolver=model.resolve_delete_list,
				required=True,
			),
		}.items() if v.args is not None},
	)


# by Sdore, 2023-26
#   www.sdore.me
