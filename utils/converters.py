# LICENSE: https://github.com/phenom4n4n/phen-cogs/blob/master/LICENSE

import discord
from discord.ext import commands
from rapidfuzz import process
from unidecode import unidecode


class StrictRole(commands.RoleConverter):
    """
    This will accept role ID's, mentions, and perform a fuzzy search for
    roles within the guild and return a list of role objects
    matching partial names
    """

    def __init__(self, response: bool = True):
        self.response = response
        super().__init__()

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        try:
            basic_role = await super().convert(ctx, argument)
            if basic_role.is_integration() or basic_role.is_bot_managed():
                raise commands.BadArgument(
                    f"`{basic_role}` is an integrated role and cannot be assigned."
                )
        except commands.BadArgument:
            pass
        else:
            return basic_role
        guild = ctx.guild
        result = [
            (r[0], r[1])
            for r in process.extract(
                argument,
                {r: unidecode(r.name) for r in guild.roles},
                limit=None,
                score_cutoff=75,
            )
        ]
        if not result:
            raise commands.BadArgument(
                f'Role "{argument}" not found.' if self.response else None
            )
        sorted_result = sorted(result, key=lambda r: r[1], reverse=True)
        sorted_result = sorted_result[0][0]
        fuzzy_role_type = discord.utils.find(
            lambda r: r.name == sorted_result, ctx.guild.roles
        )

        if (fuzzy_role_type is not None) and (
            fuzzy_role_type.is_bot_managed() or fuzzy_role_type.is_integration()
        ):
            raise commands.BadArgument(
                f"`{fuzzy_role_type}` is an integrated role and cannot be assigned."
            )
        return fuzzy_role_type
