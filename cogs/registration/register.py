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
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

import discord
from discord.app_commands import guilds
from discord.ext import commands

from utils.checks import is_botmod
from utils.context import Context

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.configuration import Configuration
    from cogs.global_actions import GlobalActions


class Registration(commands.Cog):
    def __init__(self, bot: PhantomGuard):
        self.bot: PhantomGuard = bot
        self.member_count_requirement: int = 250
        self.registering_guilds: List[int] = self.bot.registering_guilds

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_wave", id=1073732465669193818)

    def cog_load(self):
        self.registering_guilds.clear()

    def cog_unload(self):
        self.registering_guilds.clear()

    async def get_gas_cog(self, ctx: Context) -> Optional[GlobalActions]:
        cog: GlobalActions = self.bot.get_cog("GlobalActions")  # type: ignore
        if not cog:
            await ctx.reply(
                "This command is unavailable right now, try again later.",
                ephemeral=True,
            )
        return cog if cog else None

    async def get_guilds_for(
        self,
        user: discord.Member | discord.User,
        position: Literal["owners", "admins", "mods"],
        limit: int = 5,
    ) -> List[discord.Guild]:
        res = await self.bot.db.config.find_many({position: {"$all": [user.id]}})
        if not res:
            return []
        res = [self.bot.get_guild(g["_id"]) for g in res]
        res = [g for g in res if g]
        res = sorted(res, key=lambda x: x.member_count, reverse=True)
        return res[:limit] if len(res) > limit else res

    @guilds(discord.Object(id=1228685085944053882))
    @commands.hybrid_group(name="register")
    async def register(self, ctx: commands.Context) -> None:
        await ctx.send_help(ctx.command)

    @guilds(discord.Object(id=1228685085944053882))
    @register.command(name="availability")
    async def availability(self, ctx: commands.Context, guild_id: str) -> None:
        try:
            guild_id = int(guild_id)
        except ValueError:
            await ctx.reply("Guild ID must be an integer", ephemeral=True)
            return
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return

        cog: GlobalActions
        authorised = [gc for gc in cog.guild_config.keys()]
        authorised.extend(self.registering_guilds)

        if guild_id in authorised:
            guild = ctx.bot.get_guild(guild_id)
            await ctx.reply(
                f"{guild.name if guild else guild_id} is registered!", ephemeral=True
            )
            return
        else:
            await ctx.reply(f"{guild_id} is not registered!", ephemeral=True)

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @register.command(name="check")
    async def check(
        self, ctx: Context, user: discord.Member, guild: discord.Guild
    ) -> None:
        member = guild.get_member(user.id)
        if not member:
            await ctx.reply(f"could not find member in {guild.name}")
            return
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        else:
            await ctx.typing()
        ugp = member.guild_permissions
        description = (
            f"**Server**: {guild.name} (`{guild.id}`)\n"
            f"**Member Count**: @ {guild.member_count:,} members\n"
            f"**Owner**: {guild.owner.name} (`{guild.owner.id}`)\n"
            f"**Server Created at**: {discord.utils.format_dt(guild.created_at, 'f')}\n"
            f"**User Created at**: {discord.utils.format_dt(member.created_at, 'f')}\n"
            f"**User Joined at**: {discord.utils.format_dt(member.joined_at, 'f')}\n"
            f"**User Permissions**:\n"
            f"> **Administrator**: `{ugp.administrator}`\n> **Manage Guild**: `{ugp.manage_guild}`\n"
            f"> **Ban Members**: `{ugp.ban_members}`\n> **Kick Members**: `{ugp.kick_members}`\n"
            f"> **Moderate Members**: `{ugp.moderate_members}`\n> **Manage Channels**: `{ugp.manage_channels}`\n"
            f"> **Manage Webhooks**: `{ugp.manage_webhooks}`\n> **Manage Roles**: `{ugp.manage_roles}`\n"
            f"> **Manage Messages**: `{ugp.manage_messages}`\n> **Mention Everyone**: `{ugp.mention_everyone}`"
        )

        embed = discord.Embed(
            title=f"{user.name} ({user.id})'s stats",
            description=description,
            colour=discord.Colour.blurple(),
        )

        user_roles = [
            f"`{role.name}` {'**<== Highest Role**' if member.top_role and member.top_role == role else ''}"
            for role in member.roles
            if role != ctx.guild.default_role
        ]
        if user_roles:
            note = ""
            user_roles = user_roles[::-1]
            if len(user_roles) >= 20:
                note = "\nOnly the __top 20 roles__ have been taken."
            embed.add_field(
                name=f"{user.name}'s Roles [{len(user_roles)}]",
                value=", ".join(user_roles[:21]) + note,
                inline=False,
            )

        server_roles = [(f"{role.name}", role.position) for role in guild.roles]
        server_roles = sorted(server_roles, key=lambda x: x[1], reverse=True)
        if server_roles:
            roles = []
            note = ""
            for idx, role in enumerate(server_roles):
                if idx >= 20:
                    note = "\nOnly the __top 20 roles__ have been taken."
                    continue
                if idx == 0:
                    roles.append(f"`{role[0]}` **<== highest role**")
                else:
                    roles.append(f"`{role[0]}`")

            embed.add_field(
                name=f"Server Roles [{len(server_roles)}]",
                value=", ".join(roles[:21]) + note,
                inline=False,
            )

        owner_in = await self.get_guilds_for(user, "owners")
        admin_in = await self.get_guilds_for(user, "admins")
        mod_in = await self.get_guilds_for(user, "mods")

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

        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(
            text=f"{len(member.mutual_guilds):,} Mutual Servers",
            icon_url=user.display_avatar.url,
        )
        await ctx.send(embed=embed)

    async def role_helper(
        self,
        ctx: Context,
        member: discord.Member,
        position: Literal["owners", "mods", "admins"],
        guild: discord.Guild,
    ):
        found = await self.bot.db.global_actions.find(
            {
                "_id": guild.id,
            }
        )
        if not found:
            await ctx.reply("This server hasn't been registered yet!", ephemeral=False)
            return
        found = await self.bot.db.config.find(
            {
                "_id": guild.id,
            }
        )
        if not found:
            found = {"owners": [], "admins": [], "mods": []}
        found[position].append(member.id)
        for pos in found.keys():
            if pos in ["owners", "admins", "mods"]:
                found[pos] = list(set(found[pos]))
        await self.bot.db.config.upsert({"_id": guild.id}, found)

        def friendly(pos) -> List[str | discord.Role | None]:
            if pos == "owners":
                return ["Owner", ctx.guild.get_role(1229693508261249095)]
            elif pos == "admins":
                return ["Admin", ctx.guild.get_role(1229693552938975282)]
            elif pos == "mods":
                return ["Moderator", ctx.guild.get_role(1229693600586268714)]

        name, role = friendly(position)
        if role:
            try:
                await member.add_roles(
                    role, reason=f"registered as an {name} for {guild.name}"
                )
            except Exception as e:
                await ctx.reply(
                    f"An error has occurred: {e.__class__.__name__}: {e}",
                    ephemeral=False,
                )
        else:
            await ctx.reply("An error has occurred: Role Not Found", ephemeral=False)
        await ctx.reply(
            f"{member.name} is registered as an **{name}** for {guild.name}!",
            ephemeral=False,
        )

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @register.command(name="owner")
    async def owner(
        self, ctx: Context, member: discord.Member, guild: discord.Guild
    ) -> None:
        guild_member = guild.get_member(member.id)
        if not guild_member.guild_permissions.administrator:
            await ctx.reply(
                "Cannot add owner as user is missing ADMINISTRATOR permission",
                ephemeral=False,
            )
            return
        await self.role_helper(ctx, member, "owners", guild)

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @register.command(name="admin")
    async def admin(
        self, ctx: Context, member: discord.Member, guild: discord.Guild
    ) -> None:
        await self.role_helper(ctx, member, "admins", guild)

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @register.command(name="mod")
    async def mod(
        self, ctx: Context, member: discord.Member, guild: discord.Guild
    ) -> None:
        await self.role_helper(ctx, member, "mods", guild)

    async def add_to_guild_step(
        self, ctx: Context, member: discord.Member, guild_id: int
    ) -> discord.Message:
        embed = discord.Embed(
            title="Add me to your server!",
            description=f"[invite url]({discord.utils.oauth_url(
                self.bot.user.id,
                permissions=discord.Permissions(1100317073470),
                guild=discord.Object(id=guild_id)
            )})",
            colour=discord.Colour.blurple(),
        )
        return await ctx.send(
            content=member.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @register.command(name="guild", aliases=["server"])
    async def reg_guild(
        self,
        ctx: Context,
        member: discord.Member,
        guild_id: str,
        quarantine_role_id: str,
    ) -> None:
        try:
            guild_id = int(guild_id)
            quarantine_role_id = int(quarantine_role_id)
        except ValueError:
            await ctx.reply("Invalid ID(s)")
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()
        else:
            await ctx.typing()
        gas_cog = await self.get_gas_cog(ctx)
        if not gas_cog:
            return

        gas_cog: GlobalActions
        authorised = [gc for gc in gas_cog.guild_config.keys()]
        # authorised.extend(self.registering_guilds)
        if guild_id in authorised:
            await ctx.reply("This server is already registered!")
            return

        if guild_id not in self.registering_guilds:
            self.registering_guilds.append(guild_id)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            message: discord.Message = await self.add_to_guild_step(
                ctx, member, guild_id
            )

            def check(g: discord.Guild):
                return g.id == guild_id

            try:
                guild = await self.bot.wait_for("guild_join", check=check, timeout=300)
            except asyncio.TimeoutError:
                await ctx.send("You took too long, exiting...")
                return
            humans = [mem for mem in guild.members if not mem.bot]
            if len(humans) < self.member_count_requirement:
                self.registering_guilds.remove(guild_id)
                await guild.leave()
                embed = discord.Embed(
                    title="Missing Requirement",
                    description=f"I have left **{guild.name}** as it didn't meet the requirement"
                    f" of  {self.member_count_requirement} members.\nYou have {len(humans)} Human Members.",
                    colour=discord.Colour.blurple(),
                )
                await message.edit(embed=embed)
                return

        quarantine_role = guild.get_role(quarantine_role_id)

        if not quarantine_role:
            self.registering_guilds.remove(guild_id)
            await guild.leave()
            embed = discord.Embed(
                title="Missing Requirement",
                description=f"I have left **{guild.name}** as the quarantine role {quarantine_role_id} "
                f"couldn't be found",
                colour=discord.Colour.blurple(),
            )
            await ctx.send(content=member.mention, embed=embed)
            return

        config_cog = self.bot.get_cog("Configuration")
        if not config_cog:
            await ctx.reply("This feature is currently unavailable.")
            return
        config_cog: Configuration
        result = await config_cog.fix_quarantine_role(guild, quarantine_role)
        if result.get("error"):
            await ctx.send(result["error"])
            return
        await ctx.send(
            f"Fixed quarantine role in {result['success']:,} channels.\n"
            f"{result['neutral']:,} channels didn't need a modification\n"
            f"\nSkipped {result['failed']:,} Channels."
        )

        subscribed_to: Dict[str, Dict[str, bool]] = {}
        for category in gas_cog.categories:
            subscribed_to[category] = {}
            for sb in gas_cog.categories[category]:
                subscribed_to[category][sb] = True
        await self.bot.db.global_actions.insert(
            {
                "_id": guild.id,
                "quarantine_role": quarantine_role.id,
                "modlog_channel": None,
                "modlog_webhook": None,
                "categories": subscribed_to,
                "otp_in": True,
            }
        )
        gas_cog.add_config(guild, quarantine_role, subscribed_to)
        embed = discord.Embed(
            title="Server Configuration",
            description=(
                "This guild is now registered!\n"
                f"**Quarantine role**: `{quarantine_role.name}`\n"
                f"**modlog_channel**: `None`\n"
                f"**opt_in**: `True`"
            ),
        )
        category_field = []
        for category, subcategories in subscribed_to.items():
            following_subcategories = []
            for sb in subcategories:
                if subcategories[sb]:
                    following_subcategories.append(f"`{sb}`")
            if following_subcategories:
                category_field.append(
                    f"**{category.capitalize()}**: {ctx.humanize_list(following_subcategories)}"
                )
        if category_field:
            category_field = "\n".join(category_field)
        embed.add_field(name="Categories You Are Following:", value=category_field)
        await ctx.send(content=member.mention, embed=embed)
