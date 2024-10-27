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

import asyncio
from typing import TYPE_CHECKING, Literal, Optional

import discord
from discord.app_commands import describe, guilds
from discord.ext import commands

from utils.checks import is_botadmin
from utils.context import Context

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.global_actions import GlobalActions


class Admin(commands.Cog):
    def __init__(self, bot: PhantomGuard) -> None:
        self.bot: PhantomGuard = bot

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_owner", id=1133478410665066537)

    """ DAA PING ON MEMBER ROLE"""

    @commands.Cog.listener(name="on_member_update")
    async def ping_on_role(self, before: discord.Member, after: discord.Member) -> None:
        member_role = after.guild.get_role(1229192658551836792)
        if member_role not in before.roles and member_role in after.roles:
            channels = [
                1239343025474506894,  # about
                1228764652767416363,  # role
                1229425336807329853,  # register
                1239541902467006484,  # guide
                1239052941059686431,  # staff-apply
            ]
            tasks = [
                chan.send(
                    after.mention,
                    delete_after=1,
                    allowed_mentions=discord.AllowedMentions(users=[after]),
                )
                for chan in [after.guild.get_channel(c) for c in channels]
                if chan
            ]
            await asyncio.gather(*tasks)

    """ ADMIN COG """

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @commands.hybrid_group(aliases=["bl"], hidden=True)
    async def admin(self, ctx: Context) -> None:
        """Commands for managing bot's administrator commands."""

        if not ctx.subcommand_passed:
            await ctx.send_help(ctx.command)

    """ Category related commands """

    async def get_gas_cog(self, ctx: Context) -> Optional[GlobalActions]:
        cog: GlobalActions = self.bot.get_cog("GlobalActions")  # type: ignore
        if not cog:
            await ctx.reply(
                "This command is unavailable right now, try again later.",
                ephemeral=True,
            )
        return cog if cog else None

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @admin.group(name="add", invoke_without_command=True)
    async def _add(self, ctx: Context) -> None:
        await ctx.send_help("add")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @admin.group(name="remove", invoke_without_command=True)
    async def _remove(self, ctx: Context) -> None:
        await ctx.send_help("remove")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @describe(
        category="The main category to add",
        sub_categories="The initial sub categories associated with this category."
        " Seperated with a space. e.g: sub_1 sub_2",
    )
    @_add.command(name="category")
    async def add_category(
        self, ctx: Context, category: str, sub_categories: str
    ) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        category = category.lower()
        sub_categories = sub_categories.lower()
        if category in cog.categories:
            await ctx.reply("This category already exists", ephemeral=True)
            return
        else:
            sub_categories = cog.sanitize_subcategories(sub_categories)
            if not sub_categories:
                await ctx.reply("No subcategory found!", ephemeral=True)
                return
        cog.categories[category] = sub_categories
        await self.bot.db.categories.insert(
            {"_id": category, "categories": sub_categories}
        )
        await ctx.reply(
            f"Added {category} with the following subcategories: {sub_categories}"
        )

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @describe(
        category="The main category to add the sub categories to.",
        sub_categories="The sub categories to add associated with this category.",
    )
    @_add.command(name="subcategory")
    async def add_subcategory(
        self, ctx: Context, category: str, sub_categories: str
    ) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)

        category = category.lower()
        sub_categories = sub_categories.lower()

        if category not in cog.categories:
            await ctx.reply("This category doesn't exists", ephemeral=True)
            return
        else:
            sub_categories = cog.sanitize_subcategories(sub_categories)
            sub_categories.extend(cog.categories[category])
            sub_categories = cog.sanitize_subcategories(" ".join(sub_categories))
            if not sub_categories:
                await ctx.reply("No subcategory found!", ephemeral=True)
                return
        cog.categories[category] = sub_categories
        await self.bot.db.categories.upsert(
            {"_id": category}, {"_id": category, "categories": sub_categories}
        )
        await ctx.reply(f"added the subcategories: {sub_categories} to {category}")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @describe(
        category="The main category to add",
        sub_categories="The initial sub categories associated with this category."
        " Seperated with a space. e.g: sub_1 sub_2",
    )
    @_remove.command(name="category")
    async def remove_category(self, ctx: Context, category: str) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)

        category = category.lower()

        if category not in cog.categories:
            await ctx.reply("This category doesn't exists", ephemeral=True)
            return
        else:
            del cog.categories[category]
            await self.bot.db.categories.delete(
                {
                    "_id": category,
                }
            )
        await ctx.reply(f"Deleted the category {category}!")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @describe(
        category="The main category to add the sub categories to.",
        sub_categories="The sub categories to add associated with this category.",
    )
    @_remove.command(name="subcategory")
    async def remove_subcategory(
        self, ctx: Context, category: str, sub_categories: str
    ) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)

        category = category.lower()
        sub_categories = sub_categories.lower()

        if category not in cog.categories:
            await ctx.reply("This category doesn't exists", ephemeral=True)
            return
        else:
            sub_categories = cog.sanitize_subcategories(sub_categories)
            if not sub_categories:
                await ctx.reply("No subcategory found!", ephemeral=True)
                return
        all_subcategories = cog.categories[category]
        final = []
        for sb in all_subcategories:
            if sb in sub_categories:
                continue
            final.append(sb)

        await self.bot.db.categories.upsert(
            {
                "_id": category,
            },
            {"_id": category, "categories": final},
        )
        await ctx.reply(f"removed the subcategories {sub_categories} from {category}")

    """ bot mod add / remove """

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @_add.command(name="botmod")
    async def botmod_add(
        self, ctx: Context, user: discord.Member | discord.User
    ) -> None:
        if user.id in self.bot.mods or user.id in self.bot.admins:
            await ctx.reply(f"{user.mention} is already a bot mod.")
            return
        else:
            self.bot.mods.append(user.id)
            await ctx.bot.db.mods.insert(
                {
                    "_id": user.id,
                }
            )
            await ctx.reply(f"{user.mention} is now a bot mod.")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @_remove.command(name="botmod")
    async def botmod_remove(
        self, ctx: Context, user: discord.Member | discord.User
    ) -> None:
        if user.id not in self.bot.mods or user.id in self.bot.admins:
            await ctx.reply(f"{user.mention} is not a bot mod.")
            return
        else:
            self.bot.mods.remove(user.id)
            await ctx.bot.db.admins.delete(
                {
                    "_id": user.id,
                }
            )
            await ctx.reply(f"{user.mention} is no longer a bot mod.")

    """ Blacklist related commands """

    @is_botadmin()
    @admin.command()
    async def botban(
        self, ctx: Context, _id: str, _type: str, *, reason: str = None
    ) -> None:
        """Adds the given ID and type to blacklist"""
        try:
            _id = int(_id)
        except ValueError:
            await ctx.reply("Invalid ID")
            return
        if _id in self.bot.admins:
            await ctx.reply("You cannot bot ban a bot admin!")
            return
        added = await self.bot.blacklist.add_to_blacklist(_id, _type, reason)
        await ctx.send(added)

    @is_botadmin()
    @admin.command(aliases=["del"])
    async def botunban(self, ctx: Context, _id: str, _type: str) -> None:
        """Removes the given ID and type from the blacklist."""
        try:
            _id = int(_id)
        except ValueError:
            await ctx.reply("Invalid ID")
            return
        removed = await self.bot.blacklist.remove_from_blacklist(_id, _type)
        await ctx.send(removed)

    @is_botadmin()
    @admin.command()
    async def banbyref(self, ctx: Context, case_id: int, reason: str = None) -> None:
        """Bot bans someone by poll reference!"""
        found = await self.bot.db.pollings.find({"_id": case_id})
        if not found:
            await ctx.reply("No poll found with that reference!")
            return
        if found["owner"] in self.bot.admins:
            await ctx.reply("You cannot ban a bot admin!")
            return
        added = await self.bot.blacklist.add_to_blacklist(
            found["owner"], "user", reason
        )
        await ctx.send(added)

    @guilds(discord.Object(id=1228685085944053882))
    @is_botadmin()
    @admin.command(aliases=["view"])
    async def banshow(
        self, ctx: Context, option: Literal["user", "guild"] = None
    ) -> None:
        """Shows the current blacklisted users, servers etc. If no filter option is given."""

        data = await self.bot.blacklist.show_records(option)
        embed = discord.Embed(title="Current Blacklist", color=discord.Color.blurple())
        embed.description = data
        embed.set_footer(text=f"Total Entries: {self.bot.blacklist.total()}")
        await ctx.send(embed=embed)
