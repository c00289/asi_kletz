"""Built-in CRUD and introspection commands."""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result, merge_data, parse_kv
from .factory import register_command

ENTITY = Argument("entity", "Entity name (see `schema`)", required=True)
ROW_ID = Argument("id", "Row id", required=True, type="int")
DATA = Argument("data", "Row as a JSON object", flag=True, type="json")
SET = Argument("set", "Field value as key=value (repeatable)", flag=True, type="kv", multiple=True)
FILTER = Argument("filter", "Only rows where key=value (repeatable)", flag=True, type="kv", multiple=True)


@register_command
class ListCommand(Command):
    verb = "list"
    help = "List rows of an entity."
    arguments = (
        ENTITY,
        FILTER,
        Argument("order-by", "Field to sort by; prefix with - for descending", flag=True),
        Argument("limit", "Maximum rows", flag=True, type="int"),
        Argument("offset", "Rows to skip", flag=True, type="int", default=0),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.service(args["entity"])
        rows = service.list(
            parse_kv(args.get("filter")), args.get("order_by"), args.get("limit"), args.get("offset") or 0
        )
        return Result.success(rows)


@register_command
class CountCommand(Command):
    verb = "count"
    help = "Count rows of an entity."
    arguments = (ENTITY, FILTER)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.service(args["entity"])
        return Result.success({"entity": service.schema.name, "count": service.count(parse_kv(args.get("filter")))})


@register_command
class GetCommand(Command):
    verb = "get"
    help = "Fetch one row by id."
    arguments = (ENTITY, ROW_ID)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success(ctx.brain.service(args["entity"]).get(int(args["id"])))


@register_command
class CreateCommand(Command):
    verb = "create"
    help = "Create a row from --data JSON and/or --set key=value."
    arguments = (ENTITY, DATA, SET)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        row, warnings = ctx.brain.service(args["entity"]).create(merge_data(args), ctx.actor)
        return Result.success(row, warnings)


@register_command
class UpdateCommand(Command):
    verb = "update"
    help = "Update fields of a row from --data JSON and/or --set key=value."
    arguments = (ENTITY, ROW_ID, DATA, SET)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        data = merge_data(args)
        if not data:
            return Result.failure("nothing to update: pass --data or --set")
        row, warnings = ctx.brain.service(args["entity"]).update(int(args["id"]), data, ctx.actor)
        return Result.success(row, warnings)


@register_command
class DeleteCommand(Command):
    verb = "delete"
    help = "Delete a row by id."
    arguments = (ENTITY, ROW_ID)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.service(args["entity"])
        service.delete(int(args["id"]), ctx.actor)
        return Result.success({"entity": service.schema.name, "deleted": int(args["id"])})


@register_command
class SchemaCommand(Command):
    verb = "schema"
    help = "Describe all entities, or one entity, plus lookups and command signatures."
    arguments = (Argument("entity", "Entity name (optional)"),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        if args.get("entity"):
            schema = ctx.brain.registry.get(args["entity"])
            lookups = {s.lookup: list(ctx.brain.lookups.get(s.lookup, ())) for s in schema.fields if s.lookup}
            return Result.success({**schema.to_dict(), "lookups": lookups})
        return Result.success({
            **ctx.brain.registry.to_dict(),
            "lookups": ctx.brain.lookups.to_dict(),
            "commands": ctx.brain.dispatcher.factory.signatures(),
        })


@register_command
class StatusCommand(Command):
    verb = "status"
    help = "Health: version, database, row counts, recent audit entries."
    arguments = ()

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success(ctx.brain.status())
