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

from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from utils.checks import custom_check

from .views import UserProfileView

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.registration import Registration
    from utils.context import Context


class Miscellaneous(commands.Cog):
    def __init__(self, bot: PhantomGuard):
        self.bot: PhantomGuard = bot

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_pin", id=1133480760024772713)

    @custom_check()
    @commands.bot_has_permissions(embed_links=True, send_messages=True)
    @commands.hybrid_command(name="ui", aliases=["whois"])
    async def ui(
        self, ctx: Context, user: Optional[discord.User], ephemeral: bool = False
    ) -> None:
        if not user:
            user = ctx.author
        if user.bot:
            await ctx.reply("A bot... really?", ephemeral=True)
            return
        if ctx.interaction:
            await ctx.defer(ephemeral=ephemeral)
        else:
            await ctx.typing()

        impersonation_protection = await ctx.bot.db.impersonation.find({"_id": user.id})
        impersonation_enabled = bool(impersonation_protection)
        account_locked = "N/A"
        if impersonation_enabled:
            account_locked = not impersonation_protection["enabled"]
        embed = discord.Embed(
            title=f"{user.name} (`{user.id}`)",
            description=(
                f"**Created at**: {discord.utils.format_dt(user.created_at, 'R')}\n"
                f"**Mutual Servers: {len(user.mutual_guilds)}**\n"
                f"**Impersonation Protection**: `{impersonation_enabled}`\n"
                f"**Account is being impersonated**: `{account_locked}`"
            ),
            colour=discord.Color.blurple(),
        )
        # linked reports
        linked_reports = await self.bot.db.reports.find_many(
            {"reported_users": {"$all": [user.id]}}
        )
        # get the _ids for reports where action was not None
        _ids = [
            str(rep["_id"])
            for rep in linked_reports
            if [
                sanction
                for sanction in rep["sanctions"]
                if sanction["action"] != "none" and user.id in sanction["users"]
            ]
        ]
        if _ids:
            if len(_ids) > 15:
                _ids = _ids[:15]
                _ids.append(f"{len(_ids[15:]):,} more...")
            embed.add_field(name="**Linked Reports**", value=ctx.humanize_list(_ids))
        else:
            embed.add_field(name="**Linked Reports**", value="None")

        register_cog: commands.Cog | None = self.bot.get_cog("Registration")
        if register_cog:
            register_cog: Registration
            owner_in = await register_cog.get_guilds_for(user, "owners", limit=15)
            admin_in = await register_cog.get_guilds_for(user, "admins", limit=15)
            mod_in = await register_cog.get_guilds_for(user, "mods", limit=15)

            embed.add_field(
                name="DDA Roles",
                value=(
                    (
                        f"Owner: {', '.join([f"`{g.name}`" for g in owner_in]) + '\n'}"
                        if owner_in
                        else ""
                    )
                    + (
                        f"Admin: {', '.join([f"`{g.name}`" for g in admin_in]) + '\n'}"
                        if admin_in
                        else ""
                    )
                    + (
                        f"Mod: {', '.join([f"`{g.name}`" for g in mod_in]) + '\n'}"
                        if mod_in
                        else ""
                    )
                ).strip()
                if any([owner_in, admin_in, mod_in])
                else "None",
            )
        else:
            embed.add_field(
                name="DDA Roles",
                value="This feature is currently unavailable, try again later.",
            )

        # Previous Accounts

        previous_accounts = await ctx.bot.db.impersonation.find_many(
            {
                "claimed_by": user.id,
            }
        )
        if previous_accounts:
            previous_accounts = [f"`{prev['_id']}`" for prev in previous_accounts]
            if len(previous_accounts) > 15:
                previous_accounts = previous_accounts[:15]
            previous_accounts = ctx.humanize_list(previous_accounts)
            embed.add_field(name="Previous Accounts", value=previous_accounts)
        else:
            embed.add_field(name="Previous Accounts", value="None")

        data = await self.bot.db.user_profile.find({"_id": user.id})
        if not data:
            data = {"resume": None, "for_hire": None}
        view = UserProfileView(ctx, user, data["resume"], data["for_hire"])
        await ctx.send(embed=embed, view=view, ephemeral=ephemeral)

    @custom_check()
    @commands.hybrid_command(name="staff-for")
    async def staff_for(
        self, ctx: Context, guild: discord.Guild, ephemeral: bool = False
    ) -> None:
        if ctx.interaction:
            await ctx.defer(ephemeral=ephemeral)

        embed = discord.Embed(
            title=f"{guild.name} (`{guild.id}`)",
        )
        found = await self.bot.db.config.find({"_id": guild.id})
        if not found:
            await ctx.send("Guild not registered!", ephemeral=ephemeral)
            return

        if found["owners"]:
            owners = [
                guild.get_member(owner).name if guild.get_member(owner) else str(owner)
                for owner in found["owners"]
            ]
            embed.add_field(name="Owners", value=ctx.humanize_list(owners))
        else:
            embed.add_field(name="Owners", value="None")
        if found["admins"]:
            admins = set(
                guild.get_member(admin).name if guild.get_member(admin) else str(admin)
                for admin in found["admins"]
            )
            embed.add_field(name="Admins", value=ctx.humanize_list(admins))
        else:
            embed.add_field(name="Admins", value="None")
        if found["mods"]:
            mods = set(
                guild.get_member(mod).name if guild.get_member(mod) else str(mod)
                for mod in found["mods"]
            )
            embed.add_field(name="Mods", value=ctx.humanize_list(mods))
        else:
            embed.add_field(name="Mods", value="None")

        await ctx.send(embed=embed, ephemeral=ephemeral)
