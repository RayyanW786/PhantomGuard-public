# MIT License

# Copyright (c) 2024-present Rayyan

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar

from discord import app_commands
from discord.ext import commands

from .context import Context

if TYPE_CHECKING:
    from .context import GuildContext

T = TypeVar("T")


def custom_check(
    check=True,
    owneronly=False,
    guildonly=True,
    botowneronly=False,
    regowner=False,
    regadmin=False,
    regmod=False,
    **perms,
):
    """
    check - this toggles if the command can be enabled or disabled as well as if it can be used in tags
    owneronly - restricted to server owner
    guildonly - restricted to guild owner
    botowneronly - only for bot owners
    regowner - Guild owner or Registered DDA Owner
    regadmin - Guild Owner or Registered DDA Admin
    regmod - Guild Owner or Registered DDA Admin
    **perms - discord permissions
    """

    async def pred(ctx: Context):
        pred.check = check
        pred.owneronly = owneronly
        pred.perms = perms
        if ctx.author.id in ctx.bot.owner_ids:
            return True

        if botowneronly:
            raise commands.NotOwner()

        if ctx.guild is None and guildonly:
            raise commands.NoPrivateMessage()

        if owneronly:
            return ctx.guild.owner == ctx.author

        if regowner or regadmin or regmod:
            if ctx.guild.owner == ctx.author:
                return True

            guild_config = await ctx.bot.db.config.find({"_id": ctx.guild.id})

            if regowner:
                return ctx.author.id in guild_config["owners"] and (
                    await commands.has_permissions(administrator=True).predicate(ctx)
                )
            if regadmin:
                if ctx.author.id in guild_config["owners"] and (
                    await commands.has_permissions(administrator=True).predicate(ctx)
                ):
                    return True
                return ctx.author.id in guild_config["admins"]
            if regmod:
                if (
                    ctx.author.id in guild_config["owners"]
                    and (
                        await commands.has_permissions(administrator=True).predicate(
                            ctx
                        )
                    )
                ) or ctx.author.id in guild_config["admins"]:
                    return True
                return ctx.author.id in guild_config["mods"]

        if check:
            # if this is true command is allowed to be bypassed / disabled
            # check if command is disabled
            # at this point the command is not bypassed or disabled for the user so normal permissions apply
            # [ Code omitted ]
            ...

        return await commands.has_permissions(**perms).predicate(ctx)

    pred.__name__ = custom_check.__name__
    return commands.check(pred)


def is_botadmin():
    async def predicate(ctx: Context):
        return ctx.author.id in ctx.bot.admins

    return commands.check(predicate)


def is_botmod():
    async def predicate(ctx: Context):
        return ctx.author.id in ctx.bot.mods or ctx.author.id in ctx.bot.admins

    return commands.check(predicate)


async def check_permissions(ctx: GuildContext, perms: dict[str, bool], *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    resolved = ctx.channel.permissions_for(ctx.author)
    return check(
        getattr(resolved, name, None) == value for name, value in perms.items()
    )


def has_permissions(*, check=all, **perms: bool):
    async def pred(ctx: GuildContext):
        return await check_permissions(ctx, perms, check=check)

    return commands.check(pred)


async def check_guild_permissions(
    ctx: GuildContext, perms: dict[str, bool], *, check=all
):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        return False

    resolved = ctx.author.guild_permissions
    return check(
        getattr(resolved, name, None) == value for name, value in perms.items()
    )


def has_guild_permissions(*, check=all, **perms: bool):
    async def pred(ctx: GuildContext):
        return await check_guild_permissions(ctx, perms, check=check)

    return commands.check(pred)


# These do not take channel overrides into account


def hybrid_permissions_check(**perms: bool) -> Callable[[T], T]:
    async def pred(ctx: GuildContext):
        return await check_guild_permissions(ctx, perms)

    def decorator(func: T) -> T:
        commands.check(pred)(func)
        app_commands.default_permissions(**perms)(func)
        return func

    return decorator
