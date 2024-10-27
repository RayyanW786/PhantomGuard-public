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
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import discord
from discord.app_commands import describe
from discord.ext import commands, tasks

from utils.checks import custom_check
from utils.context import Context
from utils.converters import StrictRole

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.global_actions import GlobalActions, GuildConfig


class RoleMemberConverter(commands.Converter):
    async def convert(
        self, ctx: Context, argument: str
    ) -> Optional[discord.Role | discord.Member | discord.User]:
        converters = [StrictRole, commands.MemberConverter, commands.UserConverter]
        for conv in converters:
            try:
                res = await conv().convert(ctx, argument)
            except Exception:
                res = None
                # raise commands.BadArgument(str(e))
                # pass
            if res:
                return res
        raise commands.BadArgument()


class Configuration(commands.Cog):
    """
    All settings related commands.
    """

    def __init__(self, bot: PhantomGuard) -> None:
        self.bot = bot
        self.registering_guilds: List[int] = self.bot.registering_guilds
        self.webhook_avatar: Optional[bytes] = None

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_gear", id=1077240275518365797)

    # DDA Config Code
    @tasks.loop(hours=1)
    async def leave_guilds(self) -> None:
        await self.leave_unauthorised_guilds()

    @leave_guilds.before_loop
    async def before_leave_guilds(self) -> None:
        await self.bot.wait_until_ready()

    async def leave_unauthorised_guilds(self, retry=False) -> None:
        cog = self.bot.get_cog("GlobalActions")
        if not cog:
            return
        cog: GlobalActions
        authorised = [gc for gc in cog.guild_config.keys()]
        if not authorised:
            if not retry:
                await asyncio.sleep(5)
                await self.leave_unauthorised_guilds(retry=True)
            return
        authorised.extend(self.registering_guilds)
        authorised.append(1228685085944053882)
        for guild in self.bot.guilds:
            if guild.id not in authorised:
                try:
                    await guild.leave()
                except discord.HTTPException:
                    continue

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        cog = self.bot.get_cog("GlobalActions")
        if not cog:
            try:
                await guild.leave()
            except discord.HTTPException:
                pass
            return

        cog: GlobalActions
        authorised = [gc for gc in cog.guild_config.keys()]
        authorised.extend(self.registering_guilds)
        if guild.id not in authorised:
            try:
                await guild.leave()
            except discord.HTTPException:
                pass

    async def _set_webhook_avatar_task(self) -> None:
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(1228685085944053882)
        if guild:
            self.webhook_avatar = await guild.icon.read()
        else:
            self.webhook_avatar = await self.bot.user.avatar.read()

    async def cog_load(self) -> None:
        """Check If any invalid guilds have added the bot"""
        asyncio.create_task(self._set_webhook_avatar_task())
        if not self.leave_guilds.is_running():
            self.leave_guilds.start()

    async def cog_unload(self) -> None:
        if self.leave_guilds.is_running():
            self.leave_guilds.stop()

    @staticmethod
    async def fix_quarantine_role(
        guild: discord.Guild,
        role: discord.Role,
    ) -> Dict[str, Any]:
        if role > guild.me.top_role:
            return {"error": f"I must be higher than {role.name}, in role hierarchy"}
        total_roles = len(guild.roles) - 1
        if total_roles - guild.me.top_role.position > 10:
            return {"error": "My highest role must be one of the top 10 roles."}
        elif total_roles - role.position > 10:
            return {"error": f"{role.name} must be one of the top 10 roles."}

        if role.permissions != discord.Permissions.none():
            try:
                await role.edit(permissions=discord.Permissions.none())
            except (discord.Forbidden, discord.HTTPException):
                return {
                    "error": f"Failed to remove all permissions from {role.name}.\nIt cannot have any permissions!"
                }

        channels = guild.channels
        counter = {"success": 0, "neutral": 0, "failed": 0}
        for channel in channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
            overwrites = channel.overwrites
            overwrite: discord.PermissionOverwrite = overwrites.get(
                role, discord.PermissionOverwrite()
            )
            changes_needed = False
            if isinstance(channel, discord.TextChannel):
                if any(
                    [
                        overw is True or overw is None
                        for overw in (
                            overwrite.view_channel,
                            overwrite.send_messages,
                            overwrite.create_private_threads,
                            overwrite.create_private_threads,
                            overwrite.send_messages_in_threads,
                            overwrite.create_instant_invite,
                        )
                    ]
                ):
                    overwrite.view_channel = False
                    overwrite.send_messages = False
                    overwrite.create_public_threads = False
                    overwrite.create_private_threads = False
                    overwrite.send_messages_in_threads = False
                    overwrite.create_instant_invite = False
                    overwrites[role] = overwrite
                    changes_needed = True
            else:
                if any(
                    [
                        overw is True or overw is None
                        for overw in (
                            overwrite.view_channel,
                            overwrite.send_messages,
                            overwrite.create_instant_invite,
                        )
                    ]
                ):
                    overwrite.view_channel = False
                    overwrite.send_messages = False
                    overwrite.create_instant_invite = False
                    overwrites[role] = overwrite
                    changes_needed = True
            if changes_needed:
                try:
                    await channel.edit(
                        overwrites=overwrites,
                        reason="Sanitising Channel's Quarantine Override",
                    )
                except discord.Forbidden:
                    return {
                        "error": "I am missing permissions to edit the channel's overwrites"
                    }
                except discord.HTTPException:
                    counter["failed"] += 1
                    continue
                else:
                    counter["success"] += 1
            else:
                counter["neutral"] += 1

        return counter

    @custom_check(administrator=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_group(
        name="config",
        aliases=["conf"],
        case_insensitive=True,
        invoke_without_command=True,
        with_app_command=True,
    )
    async def _config(self, ctx: Context) -> None:
        """Configuration commands."""
        await ctx.send_help("config")

    async def get_gas_cog(self, ctx: Context) -> Optional[GlobalActions]:
        cog: GlobalActions = self.bot.get_cog("GlobalActions")  # type: ignore
        if not cog:
            await ctx.reply(
                "This command is unavailable right now, try again later.",
                ephemeral=True,
            )
        return cog if cog else None

    async def get_config_for(self, ctx: Context) -> Optional[GuildConfig]:
        cog = await self.get_gas_cog(ctx)
        if cog:
            guild_config = cog.guild_config
            to_return = (
                guild_config[ctx.guild.id] if ctx.guild.id in guild_config else None
            )
            if to_return:
                return to_return
        await ctx.reply(
            "This server doesn't have a config, make sure you have registered the server in DDA!",
            ephemeral=True,
        )
        return None

    async def save_config(self, ctx: Context, config: GuildConfig) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            await ctx.reply(
                "This feature is unavailable right now, try again later.",
                ephemeral=True,
            )
            return None
        cog.set_config(ctx.guild.id, config)
        friendly = {}
        for key, value in config.items():
            if key == "modlog_webhook":
                if value:
                    friendly[key] = value.url
            elif key == "modlog_channel":
                if value:
                    friendly[key] = value.id
            else:
                friendly[key] = value
        await self.bot.db.global_actions.upsert({"_id": ctx.guild.id}, friendly)

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        send_messages=True,
        embed_links=True,
        manage_webhooks=True,
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @describe(
        user="The user you wish to locally appeal!",
        case_id="The case ID you wish to locally appeal for this user!",
    )
    @_config.command(name="remove-sanction")
    async def remove_sanction(
        self, ctx: Context, user: discord.User, case_id: int
    ) -> None:
        """Locally remove a sanction from a user for a specific case ID"""
        if ctx.interaction:
            await ctx.defer(ephemeral=False)

        report = await self.bot.db.reports.find(
            {"_id": case_id, "reported_users": {"$all": [user.id]}}
        )
        if not report:
            await ctx.reply("Invalid Case ID!")
            return
        action_type = None
        for sanction in report["sanctions"]:
            if user.id in sanction["users"]:
                action_type = sanction["action"]
                break
        if not action_type:
            await ctx.reply("Could not find a action_type for user!")
            return
        if action_type not in ["ban", "kick", "quarantine", "mute"]:
            await ctx.reply("No persistent action_type for user found!")
            return

        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        cog: GlobalActions

        member = ctx.guild.get_member(user.id)

        if action_type == "ban":
            if ctx.guild.me.guild_permissions.ban_members:
                try:
                    ban_entry = await ctx.guild.fetch_ban(user)
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    pass
                else:
                    if f"[Report {case_id}'s Action]!" in ban_entry.reason:
                        try:
                            await ctx.guild.unban(
                                discord.Object(user.id),
                                reason=f"Ban Removed by {ctx.author.id}! Case ID: {case_id}",
                            )
                        except (
                            discord.Forbidden,
                            discord.NotFound,
                            discord.HTTPException,
                        ):
                            pass

        elif action_type == "quarantine" and member:
            if ctx.guild.me.guild_permissions.manage_roles:  # noqa: ignore
                if ctx.guild.me.top_role > member.top_role:
                    quarantine_role = cog.guild_config[ctx.guild.id]["quarantine_role"]
                    if quarantine_role:
                        quarantine_role = ctx.guild.get_role(quarantine_role)
                        if quarantine_role:
                            try:
                                await member.remove_roles(
                                    quarantine_role,
                                    reason=f"Quarantine Removed by {ctx.author.id}! Case ID: {case_id}",
                                )
                            except (discord.Forbidden, discord.HTTPException):
                                pass
                            restore_result = await cog.restore_from_save(
                                ctx.guild, member, case_id=case_id
                            )
                            await cog.on_restore(
                                ctx.guild, member, case_id, restore_result
                            )
        elif action_type == "mute" and member:
            # when action-type.Mute we don't need to unmute as that is handled by discord
            # However we need to give their roles back!
            restore_result = await cog.restore_from_save(
                ctx.guild, member, case_id=case_id
            )
            await cog.on_restore(ctx.guild, member, case_id, restore_result)

        await cog.delete_sanction(ctx.guild, user.id, action_type, case_id)

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        manage_webhooks=True,
        send_messages=True,
        embed_links=True,
        ban_members=True,
        kick_members=True,
        manage_roles=True,
        moderate_members=True,
        manage_channels=True,
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @describe(option="opp into global actions: True or False")
    @_config.command(name="opt-in")
    async def opt_in(self, ctx: Context, option: bool) -> None:
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        config = await self.get_config_for(ctx)
        if not config:
            return
        config["otp_in"] = option
        await self.save_config(ctx, config)
        await ctx.reply(f"Set OPT-IN as {option}", ephemeral=True)

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        manage_webhooks=True, send_messages=True, embed_links=True
    )
    @describe(modlog="The channel where DDA logs are sent.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command(name="modlog")
    async def modlog(self, ctx: Context, modlog: discord.TextChannel) -> None:
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        config = await self.get_config_for(ctx)
        if not config:
            return
        if not modlog.permissions_for(ctx.guild.me).manage_webhooks:
            await ctx.reply(
                f"I need MANAGE_WEBHOOK permissions for the channel {modlog.mention}"
            )
            return
        config["modlog_channel"] = modlog
        # now try to create a new webhook
        try:
            modlog_webhook = await modlog.create_webhook(
                name="DDA logs",
                avatar=self.webhook_avatar,
                reason="Create Modlog webhook for DDA logs!",
            )
        except (discord.HTTPException, discord.Forbidden):
            await ctx.reply(
                "Webhook creation failed! Please check my permissions.", ephemeral=True
            )
            return

        # try to use the webhook (maybe wick or someone else deletes it)
        await asyncio.sleep(2)  # sleep to ensure it is safe to use
        # that is if wick was to delete it, it would be done by now
        try:
            await modlog_webhook.send(
                content="Testing Webhook!",
                username="DDA Configuration Setup",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            await ctx.reply(
                "Webhook creation failed! (Make sure no other bot is deleting my webhook).",
                ephemeral=True,
            )
            return
        # new webhook created successfully
        config["modlog_webhook"] = modlog_webhook
        await self.save_config(ctx, config)
        await ctx.reply(
            f"{modlog.mention} has been set as your modlog channel", ephemeral=True
        )

    @custom_check(administrator=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @describe(
        category="The main category you wish to follow.",
        sub_categories="Type all to follow all sub categories. Split categories via space: i.e sub_cat1 sub_cat2",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command(name="follow_category")
    async def follow_category(
        self, ctx: Context, category: str, sub_categories: str
    ) -> None:
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        cog: GlobalActions

        if category not in cog.categories.keys():
            await ctx.reply(f'"{category}" does not exist', ephemeral=True)
            return
        if sub_categories == "all":
            sub_categories = cog.categories[category]
        else:
            sub_categories = cog.sanitize_subcategories(sub_categories)

        if not sub_categories:
            await ctx.reply(
                (
                    f"No valid subcategory found!\nThe category {category}"
                    f" has the following sub categories: {ctx.humanize_list(cog.categories[category])}"
                ),
                ephemeral=True,
            )
            return
        else:
            config = await self.get_config_for(ctx)
            if not config:
                return
            valid_subcategories = cog.categories[category]
            for sb in sub_categories:
                if sb in valid_subcategories:
                    config["categories"][category][sb] = True
                else:
                    await ctx.reply(
                        f'subcategory "{sb}" does not exist', ephemeral=True
                    )
                    return

            await self.save_config(ctx, config)
            await ctx.reply(
                f"You are now following the sub categories: {ctx.humanize_list(sub_categories)}"
            )

    @custom_check(administrator=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @describe(
        category="The main category you wish to unfollow.",
        sub_categories="Type all to follow all sub categories. Split categories via space: i.e sub_cat1 sub_cat2",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command(name="unfollow_category")
    async def unfollow_category(
        self, ctx: Context, category: str, sub_categories: str
    ) -> None:
        cog: GlobalActions = await self.get_gas_cog(ctx)
        if not cog:
            return
        cog: GlobalActions
        if category not in cog.categories.keys():
            await ctx.reply(f'"{category}" does not exist', ephemeral=True)
            return
        if sub_categories == "all":
            sub_categories = cog.categories[category]
        else:
            sub_categories = cog.sanitize_subcategories(sub_categories)

        if not sub_categories:
            await ctx.reply(
                (
                    f"No valid subcategory found!\nThe category {category}"
                    f" has the following sub categories: {ctx.humanize_list(cog.categories[category])}"
                ),
                ephemeral=True,
            )
            return
        else:
            config = await self.get_config_for(ctx)
            if not config:
                return
            valid_subcategories = cog.categories[category]
            for sb in sub_categories:
                if sb in valid_subcategories:
                    config["categories"][category][sb] = False
                else:
                    await ctx.reply(
                        f'subcategory "{sb}" does not exist', ephemeral=True
                    )
                    return

            await self.save_config(ctx, config)
            await ctx.reply(
                f"You are now unfollowing the sub categories: {ctx.humanize_list(sub_categories)}"
            )

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        manage_channels=True, send_messages=True, embed_links=True
    )
    @describe(role="The quarantine role.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command()
    async def setquarantinerole(self, ctx: Context, role: discord.Role) -> None:
        config = await self.get_config_for(ctx)
        if not config:
            return
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        result = await self.fix_quarantine_role(ctx.guild, role)
        if result.get("error"):
            await ctx.reply(result["error"], ephemeral=True)
            return
        config["quarantine_role"] = role.id
        await self.save_config(ctx, config)
        await ctx.reply(
            f"setup quarantine role in {result['success']:,} channels.\n"
            f"{result['neutral']:,} channels didn't need a modification\n"
            f"\nSkipped {result['failed']:,} Channels."
        )

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        manage_channels=True, send_messages=True, embed_links=True
    )
    @describe(role="The quarantine role.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command()
    async def fixquarantinerole(self, ctx: Context) -> None:
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        config = await self.get_config_for(ctx)
        if not config:
            return
        role = config["quarantine_role"]
        if not role:
            await ctx.reply(
                "You need to setup a quarantine role first...", ephemeral=True
            )
            return
        role = ctx.guild.get_role(role)
        if not role:
            await ctx.reply(
                "You need to setup a quarantine role first...", ephemeral=True
            )
            return
        result = await self.fix_quarantine_role(ctx.guild, role)
        if result.get("error"):
            await ctx.reply(result["error"], ephemeral=True)
            return
        config["quarantine_role"] = role.id
        await self.save_config(ctx, config)
        await ctx.reply(
            f"Fixed quarantine role in {result['success']:,} channels.\n"
            f"{result['neutral']:,} channels didn't need a modification\n"
            f"\nSkipped {result['failed']:,} Channels."
        )

    @custom_check(administrator=True)
    @commands.bot_has_permissions(
        send_messages=True, embed_links=True, manage_roles=True
    )
    @describe(
        role="The quarantine role.",
        skip_harmful="If the bot should skip roles that contain dangerous permissions.",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command()
    async def restoreroles(
        self, ctx: Context, member: discord.Member, skip_harmful: bool = True
    ) -> None:
        cog: GlobalActions = await self.get_gas_cog(ctx)
        if not cog:
            return
        if ctx.interaction:
            await ctx.defer()
        result = await cog.restore_from_save(
            ctx.guild, member, skip_harmful=skip_harmful, authorised_by=ctx.author
        )
        await ctx.reply(f"Role restoration completed: {result}", ephemeral=True)

    @custom_check(administrator=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    @_config.command()
    async def show(self, ctx: Context) -> None:
        config: GuildConfig = await self.get_config_for(ctx)
        if not config:
            return
        description = []
        categories_field = None
        for key, value in config.items():
            if key == "modlog_webhook":
                continue
            elif key == "modlog_channel":
                if value:
                    value = value.mention
            elif key == "quarantine_role":
                value = ctx.guild.get_role(value)
                if value:
                    value = value.mention
            if key == "categories":
                value = []
                for category, subcategories in config["categories"].items():
                    following_subcategories = []
                    for sb in subcategories:
                        if subcategories[sb]:
                            following_subcategories.append(f"`{sb}`")
                    if following_subcategories:
                        value.append(
                            f"**{category.capitalize()}**: {ctx.humanize_list(following_subcategories)}"
                        )
                if value:
                    categories_field = "\n".join(value)
            else:
                description.append(f"**{key.lower().capitalize()}**: {value}")

        embed = discord.Embed(
            title="Configuration", description="\n".join(description), colour=0x2F3136
        )
        if categories_field:
            embed.add_field(name="Categories", value=categories_field, inline=False)
        await ctx.send(embed=embed)

    # Bypass | Disable Related Code

    # [Code Omitted]

    @staticmethod
    async def deleted_role(
        ctx: Context,
        _type: Literal["bypassed", "disabled"],
        role_id: str,
        channel: Optional[str],
    ) -> None: ...

    @staticmethod
    async def deleted_channel(
        ctx: Context, _type: Literal["bypassed", "disabled"], channel_id: str
    ) -> None: ...

    @staticmethod
    def find_commands(ctx: Context, command_or_cog: str) -> set[str]: ...

    @staticmethod
    def get_pointer(
        ctx: Context,
        _type: Literal["bypassed", "disabled"],
        channel: discord.TextChannel,
    ) -> dict: ...

    # bypass

    @custom_check(check=False, administrator=True, regowner=True, guildonly=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.hybrid_group(
        name="bypass",
        case_insensitive=True,
        invoke_without_command=True,
        with_app_command=True,
    )
    async def _bypass(self, ctx: Context) -> None:
        """Add, Remove, View bypassed commands."""
        await ctx.send_help("bypass")

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_bypass.command(name="add", aliases=["+"])
    async def _addbypass(
        self,
        ctx: Context,
        channel: Optional[discord.TextChannel],
        role_or_member: Optional[RoleMemberConverter],
        *,
        command_or_cog: str,
    ) -> None:
        """Adds a command / Cog to bypass the discord Permission for a user or role.
        Provide a channel mention or id in the [channel] argument if you only want the bypass to be limited to that channel instead of the whole server."""

        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_bypass.command(name="remove", aliases=["-"])
    async def _removebypass(
        self,
        ctx: Context,
        channel: Optional[discord.TextChannel],
        role_or_member: Optional[RoleMemberConverter],
        *,
        command_or_cog: str,
    ) -> None:
        """Remove a command / Cog to bypass the discord Permission for a user or role"""
        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_bypass.command(name="list", aliases=["ls", "view", "show"])
    async def _bypasslist(self, ctx: Context) -> None:
        """Sends a paginated list of all of the bypassed commands for this server"""
        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_bypass.command(name="clear")
    async def _bypassclear(self, ctx: Context) -> None:
        """Clears all of your bypass list"""

        ...

    # disabled

    @custom_check(check=False, administrator=True, regowner=True, guildonly=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.hybrid_group(
        name="disable",
        case_insensitive=True,
        invoke_without_command=True,
        with_app_command=True,
    )
    async def _disable(self, ctx: Context) -> None:
        """Add, Remove, View disabled commands."""
        await ctx.send_help("disable")

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_disable.command(name="add", aliases=["+"])
    async def _adddisable(
        self,
        ctx: Context,
        channel: Optional[discord.TextChannel],
        role_or_member: Optional[RoleMemberConverter],
        *,
        command_or_cog: str,
    ) -> None:
        """Adds a command / Cog to disabled list for a user or role.
        Provide a channel mention or id in the [channel] argument if you only want it to be limited to that channel instead of the whole server."""

        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_disable.command(name="remove", aliases=["-"])
    async def _removedisable(
        self,
        ctx: Context,
        channel: Optional[discord.TextChannel],
        role_or_member: Optional[RoleMemberConverter],
        *,
        command_or_cog: str,
    ) -> None:
        """Remove a command / Cog from the disable list for a user or role"""

        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_disable.command(name="clear")
    async def _disableclear(self, ctx: Context) -> None:
        """Clears all of your disabled list"""

        ...

    @custom_check(check=False, administrator=True, regowner=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @_disable.command(name="list", aliases=["ls", "view", "show"])
    async def _disablelist(self, ctx: Context) -> None:
        """Sends a paginated list of all of the disabled commands for this server"""

        ...
