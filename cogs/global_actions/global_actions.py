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
import datetime
import logging
import uuid
from typing import TYPE_CHECKING, Dict, List, Never, Optional, TypedDict

import discord
from discord.ext import commands

from utils.time import human_timedelta

from .enums import Actions, AppealActions, ScopeTypes

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.reminder import Timer

log = logging.getLogger(__name__)


def generate_snowflake() -> str:
    """Generates a unique Snowflake ID"""
    timestamp = datetime.datetime.now().timestamp()
    unique_id = uuid.uuid4()
    timestamp_int = int(timestamp * 1000)
    snowflake = f"{timestamp_int}-{unique_id}"

    return snowflake


class GuildConfig(TypedDict):
    quarantine_role: Optional[int]
    otp_in: bool
    categories: Dict[str, Dict[str, bool]]
    modlog_webhook: Optional[discord.Webhook]
    modlog_channel: Optional[discord.TextChannel]


class SanctionData(TypedDict):
    target: int
    category: str
    subcategory: str
    actiontype: int
    created: datetime.datetime
    expires: datetime.datetime
    case_id: int


class FakeUser:
    def __init__(self, _id, mention):
        self.id: int = _id
        self.mention: str = mention


HARMFUL_PERMISSIONS = discord.Permissions(1100317073470)


# HARMFUL_PERMISSIONS.administrator = True
# HARMFUL_PERMISSIONS.manage_guild = True
# HARMFUL_PERMISSIONS.ban_members = True
# HARMFUL_PERMISSIONS.kick_members = True
# HARMFUL_PERMISSIONS.moderate_members = True
# HARMFUL_PERMISSIONS.manage_channels = True
# HARMFUL_PERMISSIONS.manage_webhooks = True
# HARMFUL_PERMISSIONS.manage_roles = True
# HARMFUL_PERMISSIONS.manage_messages = True
# HARMFUL_PERMISSIONS.mention_everyone = True


class GlobalActions(commands.Cog):
    def __init__(self, bot: PhantomGuard) -> None:
        self.bot: PhantomGuard = bot
        self.categories: Dict[str, List[str]] = {}
        self.guild_config: Dict[int, GuildConfig] = {}
        self.sanction_cache: Dict[int, Dict[str, SanctionData]] = {}
        self.webhook_avatar: Optional[bytes] = None
        self.webhook_creation_lock: Dict[int, asyncio.Event] = {}
        self.stats_channel: Optional[discord.TextChannel] = None

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_hammer", id=1073746771609649212)

    @staticmethod
    def sanitize_subcategories(subcategories: str) -> List[str]:
        subcategories = subcategories.strip().split(" ")
        subcategories = set(subcategories)
        new = []
        for sub in subcategories:
            if not sub:
                continue
            new.append(sub)
        return new

    async def _set_webhook_avatar_task(self):
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(1228685085944053882)
        if guild:
            self.webhook_avatar = await guild.icon.read()
        else:
            self.webhook_avatar = await self.bot.user.avatar.read()

    async def _build_cache(self):
        await self.bot.wait_until_ready()
        self.stats_channel = self.bot.get_channel(1241062053368692866)
        guild_config = await self.bot.db.global_actions.get_all()
        for config in guild_config:
            if config["modlog_channel"]:
                config["modlog_channel"] = self.bot.get_channel(
                    config["modlog_channel"]
                )
            if config["modlog_webhook"]:
                try:
                    config["modlog_webhook"] = discord.Webhook.from_url(
                        config["modlog_webhook"],
                        session=self.bot.session,
                        bot_token=self.bot.http.token,
                    )
                except (ValueError, TypeError):
                    config["modlog_webhook"] = None
                    await self.bot.db.global_actions.upsert(
                        {"_id": config["_id"]},
                        {
                            "_id": config["_id"],
                            "modlog_webhook": None,
                        },
                    )
            data = {}
            for key, value in config.items():
                if key not in [
                    "quarantine_role",
                    "otp_in",
                    "categories",
                    "modlog_channel",
                    "modlog_webhook",
                ]:
                    continue
                data[key] = value
            self.guild_config[config["_id"]] = data

        sanction_data = await self.bot.db.sanctions.get_all()
        for sanction in sanction_data:
            data = {}
            expires = sanction["expires"]
            if expires:
                expires = expires.replace(tzinfo=datetime.timezone.utc)

            data.update(
                {
                    "target": sanction["target"],
                    "actiontype": sanction["actiontype"],
                    "created": sanction["created"],
                    "expires": expires,
                    "case_id": sanction["case_id"],
                    "category": sanction["category"],
                    "subcategory": sanction["subcategory"],
                }
            )
            if sanction["guild"] not in self.sanction_cache.keys():
                self.sanction_cache[sanction["guild"]] = {}
            self.sanction_cache[sanction["guild"]][sanction["_id"]] = data

    async def cog_load(self) -> None:
        # load from db categories, and guild_config
        asyncio.create_task(self._set_webhook_avatar_task())
        asyncio.create_task(self._build_cache())
        category_data = await self.bot.db.categories.get_all()
        for category in category_data:
            self.categories[category["_id"]] = category["categories"]

    def add_config(
        self,
        guild: discord.Guild,
        quarantine_role: discord.Role,
        subscribed_to: Dict,
        **kwargs,
    ):
        self.guild_config[guild.id] = {
            "quarantine_role": quarantine_role.id,
            "otp_in": kwargs.get("otp_in", True),
            "categories": subscribed_to,
            "modlog_channel": kwargs.get("modlog_channel"),
            "modlog_webhook": kwargs.get("modlog_webhook"),
        }

    def set_config(self, guild_id: int, config: GuildConfig):
        self.guild_config[guild_id] = config

    def pred_otp(self, guild: int) -> bool:
        if guild not in self.guild_config:
            return False
        return self.guild_config[guild]["otp_in"]

    def pred_category(self, guild: int, main: str, sub: str) -> bool:
        if guild not in self.guild_config:
            return False
        return self.guild_config[guild]["categories"].get(main, {}).get(sub, False)

    async def on_strip(
        self,
        guild: discord.Guild,
        target: discord.Member,
        case_id: int,
        expires: datetime.datetime,
        success: bool,
    ):
        """called when a person's roles are stripped"""
        success_fmt = (
            "**Success**"
            if success
            else (
                "**Failed**\n"
                "As a result this server **may** have been marked OTP OUT of global actions\n"
                "Check using `/config show` and to __re-setup__ use `/config modlog [channel]` & `/config otp-in True`"
            )
        )

        content = f"DDA Report Compliance: {success_fmt}"
        description = (
            f"**Offender**: {target.mention}\n"
            + (
                (
                    f"**Duration**: {human_timedelta(expires, suffix=False, accuracy=4)}"
                    f" [ {discord.utils.format_dt(expires, 'f')}]\n"
                )
                if expires is not None
                else ""
            )
            + f"**Case ID**: {case_id}\n"
            f"Use `/report view {case_id}` to view this case."
        )

        embed = discord.Embed(
            title="**Role(s) Stripped**",
            colour=discord.Colour.green() if success else 0xFF0010,
            description=description,
        )
        embed.timestamp = discord.utils.utcnow()
        return await self.send_to_modlog(guild, content, embed)

    async def on_restore(
        self, guild: discord.Guild, target: discord.Member, case_id: int, success: bool
    ):
        """called when a person's roles are restored"""
        success_fmt = (
            "**Success**"
            if success
            else (
                "**Failed**\n"
                "As a result this server **may** have been marked OTP OUT of global actions\n"
                "Check using `/config show` and to __re-setup__ use `/config modlog [channel]` & `/config otp-in True`"
            )
        )

        content = f"DDA Restoration Compliance: {success_fmt}"
        description = (
            f"**Offender**: {target.mention}\n"
            f"**Case ID**: {case_id}\n"
            f"Use `/report view {case_id}` to view this case."
        )

        embed = discord.Embed(
            title="**Role(s) Restored**",
            colour=discord.Colour.green() if success else 0xFF0010,
            description=description,
        )
        embed.timestamp = discord.utils.utcnow()
        return await self.send_to_modlog(guild, content, embed)

    async def on_action(
        self,
        guild: discord.Guild,
        target: discord.Member | discord.User,
        actiontype: Actions,
        case_id: int,
        category: str,
        subcategory: str,
        success: bool,
        expires: Optional[datetime.datetime] = None,
    ) -> bool:
        """Helper function for sending modlogs when a sanction is completed"""
        success_fmt = (
            "**Success**"
            if success
            else (
                "**Failed**\n"
                "As a result this server **may** have been marked OTP OUT of global actions\n"
                "Check using `/config show` and to __re-setup__ use `/config modlog [channel]` & `/config otp-in True`"
            )
        )
        content = f"Discord Defence Association Report: {success_fmt}"
        description = (
            f"**Offender**: {target.mention}\n"
            + (
                (
                    f"**Duration**: {human_timedelta(expires, suffix=False, accuracy=4)}"
                    f" [ {discord.utils.format_dt(expires, 'f')}]\n"
                )
                if expires is not None
                else ""
            )
            + f"**Case ID**: {case_id}\n"
            f"**Category**: {category} [ {subcategory} ]\n"
            f"Use `/report view {case_id}` to view this case."
        )
        embed = discord.Embed(
            title=f"**{str(actiontype).capitalize()}**",
            colour=discord.Colour.green() if success else 0xFF0010,
            description=description,
        )
        embed.timestamp = discord.utils.utcnow()
        return await self.send_to_modlog(guild, content, embed)

    async def on_action_expiry(
        self,
        guild: discord.Guild,
        target: discord.Member | discord.Object,
        actiontype: Actions,
        case_id: int,
        success: bool,
    ) -> bool:
        """called when action's duration ends"""

        if isinstance(target, discord.Object):
            target = FakeUser(target.id, f"<@{target.id}>")

        success_fmt = (
            "**Success**"
            if success
            else (
                "**Failed**\n"
                "As a result this server **may** have been marked OTP OUT of global actions\n"
                "Check using `/config show` and to __re-setup__ use `/config modlog [channel]` & `/config otp-in True`"
            )
        )
        content = f"DDA Restoration Compliance: {success_fmt}"
        description = (
            f"**Offender**: {target.mention}\n"
            f"**Action Type**: {str(Actions(actiontype)).capitalize()}\n"
            f"**Case ID**: {case_id}\n"
            f"Use `/report view {case_id}` to view this case."
        )

        embed = discord.Embed(
            title=f"Action Expiry: **{str(Actions(actiontype)).capitalize()}**",
            colour=discord.Colour.green() if success else 0xFF0010,
            description=description,
        )
        embed.timestamp = discord.utils.utcnow()
        return await self.send_to_modlog(guild, content, embed)

    async def on_appeal(
        self,
        guild: discord.Guild,
        target: discord.Member | discord.User,
        appealtype: AppealActions,
        category: str,
        subcategory: str,
        case_id: int,
        success: bool,
    ) -> bool:
        """called when an appeal is accepted."""

        success_fmt = (
            "**Success**"
            if success
            else (
                "**Failed**\n"
                "As a result this server **may** have been marked OTP OUT of global actions\n"
                "Check using `/config show` and to __re-setup__ use `/config modlog [channel]` & `/config otp-in True`"
            )
        )
        content = f"DDA Appeal Compliance: {success_fmt}"
        description = (
            f"**Offender**: {target.mention}\n"
            f"**Action Type**: {str(appealtype)}\n"
            f"**Case ID**: {case_id}\n"
            f"**Category**: {category} [ {subcategory} ]\n"
            f"Use `/report view {case_id}` to view this case."
        )

        embed = discord.Embed(
            title=f"**{str(appealtype).capitalize()}**",
            colour=discord.Colour.green() if success else 0xFF0010,
            description=description,
        )
        embed.timestamp = discord.utils.utcnow()
        return await self.send_to_modlog(guild, content, embed)

    async def strip_and_save(
        self, guild: discord.Guild, target: discord.Member, case_id: int
    ) -> bool:
        if not guild.me.guild_permissions.manage_roles:
            self.guild_config[guild.id]["otp_in"] = False
            await self.bot.db.global_actions.upsert(
                {"_id": guild.id}, {"_id": guild.id, "otp_in": False}
            )
            return False

        if target.top_role > guild.me.top_role:
            return False
        else:
            roles = [r for r in target.roles if r.id != guild.default_role.id]
            if not roles:
                return True
            try:
                await target.remove_roles(
                    *roles,
                    atomic=False,
                    reason=f"Role(s) Stripped to apply Report {case_id}'s Action!"
                    f" Run /config restore-roles [user] to undo this.",
                )
                await self.bot.db.stripped_roles.upsert(
                    {"_id": target.id},
                    {
                        "_id": target.id,
                        "roles": [r.id for r in roles],
                        "when": datetime.datetime.now().timestamp(),
                    },
                )
                return True
            except discord.Forbidden:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id}, {"_id": guild.id, "otp_in": False}
                )
                return False
            except discord.HTTPException:
                return False

    async def restore_from_save(
        self,
        guild: discord.Guild,
        target: discord.Member,
        *,
        skip_harmful: bool = True,
        authorised_by: Optional[discord.Member] = None,
        case_id: Optional[int] = None,
    ) -> bool:
        found = await self.bot.db.stripped_roles.find(
            {
                "_id": target.id,
            }
        )
        if not found:
            return True
        roles = [guild.get_role(r) for r in found["roles"]]
        roles = [r for r in roles if r]
        if authorised_by is None:
            skip_harmful = True
            reason = f"Automatic role restoration for Case ID: {case_id}]! Skipping harmful roles..."
        else:
            reason = f"Role restoration executed by {authorised_by.name}! skip harmful roles: {skip_harmful}"
        if skip_harmful:
            to_add = []
            for role in roles:
                safe = role.permissions & HARMFUL_PERMISSIONS
                safe = not safe
                if safe:
                    to_add.append(role)
            await target.add_roles(*to_add, reason=reason, atomic=False)
        else:
            await target.add_roles(*roles, reason=reason, atomic=False)
        return True

    async def send_to_modlog(
        self, guild: discord.Guild, content: str, embed: discord.Embed
    ) -> bool:
        # check if a new webhook is already being created:
        result = self.webhook_creation_lock.get(guild.id, None)
        if result:
            assert isinstance(result, asyncio.Event)
            if not result.is_set():
                try:
                    await asyncio.wait_for(result.wait(), timeout=60)
                except asyncio.TimeoutError:
                    # waited too long, something must be wrong (highly unlikely)
                    # reset the guild's webhook creation lock
                    try:
                        del self.webhook_creation_lock[guild.id]
                    except KeyError:
                        pass
                    return False
        modlog_channel = self.guild_config[guild.id]["modlog_channel"]
        if not modlog_channel:
            return False
        # modlog_channel = self.bot.get_channel(modlog_channel)
        # if not modlog_channel:
        #     return False
        modlog_webhook = self.guild_config[guild.id]["modlog_webhook"]

        async def disable_modlog_and_notify():
            nonlocal content
            nonlocal embed

            self.guild_config[guild.id]["modlog_channel"] = None
            await self.bot.db.global_actions.upsert(
                {"_id": guild.id},
                {"_id": guild.id, "modlog_channel": None, "modlog_webhook": None},
            )

            if (
                modlog_channel.permissions_for(guild.me).send_messages
                and modlog_channel.permissions_for(guild.me).embed_links
            ):
                try:
                    await modlog_channel.send(content=content, embed=embed)
                except discord.Forbidden:
                    return
                except discord.HTTPException:
                    pass

                # Notify them that the Modlog's have been disabled
                notify_description = (
                    "I am __unable__ to create webhooks as `MANAGE_WEBHOOK` permission has been denied for me"
                    " or webhook creation has failed."
                    " As a result modlog's from **Discord Defence Association** will be **disabled**.\n"
                    "To enable modlog's please run `/config modlog [channel]` after providing me"
                    " with `MANAGE_WEBHOOK` Permission."
                )
                notify_embed = discord.Embed(
                    title="Modlog Disabled Alert",
                    description=notify_description,
                    colour=0xFF0010,
                )
                notify_embed.timestamp = discord.utils.utcnow()
                try:
                    await modlog_channel.send(
                        "**Warning** ⚠️", embeds=[notify_embed, embed]
                    )
                except (discord.HTTPException, discord.Forbidden):
                    pass

        failed_flag = False

        if modlog_webhook:
            try:
                await modlog_webhook.send(
                    content=content,
                    embed=embed,
                    username="DDA logs",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.NotFound):
                failed_flag = True
            except discord.HTTPException:
                return False  # Something went wrong, but webhook was fine

        if not modlog_webhook or failed_flag:
            if not modlog_channel.permissions_for(guild.me).manage_webhooks:
                await disable_modlog_and_notify()
                return False

            else:
                # create a lock first
                if self.webhook_creation_lock.get(guild.id):
                    self.webhook_creation_lock[guild.id].clear()
                else:
                    self.webhook_creation_lock[guild.id] = asyncio.Event()
                # now try to create a new webhook
                try:
                    modlog_webhook = await modlog_channel.create_webhook(
                        name="DDA logs",
                        avatar=self.webhook_avatar,
                        reason="Create Modlog webhook for DDA logs!",
                    )
                except (discord.HTTPException, discord.Forbidden):
                    await disable_modlog_and_notify()
                    self.webhook_creation_lock[guild.id].set()
                    return False

                # try to use the webhook (maybe wick or someone else deletes it)
                await asyncio.sleep(2)  # sleep to ensure it is safe to use
                # that is if wick was to delete it, it would be done by now
                try:
                    await modlog_webhook.send(
                        content=content,
                        embed=embed,
                        username="DDA logs",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except (discord.Forbidden, discord.NotFound):
                    await disable_modlog_and_notify()
                    self.webhook_creation_lock[guild.id].set()
                    return False
                except discord.HTTPException:
                    self.webhook_creation_lock[guild.id].set()
                    return False  # Something went wrong, but webhook was fine

                # new webhook created successfully
                self.guild_config[guild.id]["modlog_webhook"] = modlog_webhook
                await self.bot.db.global_actions.upsert(
                    {
                        "_id": guild.id,
                    },
                    {"modlog_webhook": modlog_webhook.url},
                )
                self.webhook_creation_lock[guild.id].set()
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id},
                    {"_id": guild.id, "modlog_webhook": modlog_webhook.url},
                )

    async def guild_sanction(
        self,
        guild: discord.Guild,
        category: str,
        subcategory: str,
        actiontype: Actions,
        target: discord.User,
        case_id: int,
        expires: Optional[datetime.datetime] = None,
    ) -> Optional[bool]:
        """
        returns:
        True - sanction successful
        False - Unable to carry out sanction
        None - Sanction doesn't apply ( user not a member of guild )

        """
        if guild.id not in self.guild_config:
            return None

        if not self.pred_otp(guild.id):
            return None

        if not self.pred_category(guild.id, category, subcategory):
            return None

        if actiontype == Actions.NONE:
            return True

        if actiontype == Actions.WARN:
            return True  # This will simply be a single DM not a DM per Guild

        member = guild.get_member(target.id)
        if member:
            target: discord.Member = member

        if actiontype == Actions.BAN:
            if isinstance(target, discord.Member):
                if target == guild.owner:  # noqa: ignore
                    return False
                elif target.top_role > guild.me.top_role:
                    return False
                result = await self.strip_and_save(guild, target, case_id)
                await self.on_strip(guild, target, case_id, expires, result)
                if not result:
                    return False
            try:
                if expires:
                    reason = (
                        f"User Banned  for {human_timedelta(expires, suffix=False, accuracy=4)} "
                        f"[Report {case_id}'s Action]!"
                    )
                    reason = "".join(reason)
                else:
                    reason = f"User Banned [Report {case_id}'s Action]!"
                await guild.ban(target, reason=reason)
                return True
            except discord.Forbidden:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id}, {"_id": guild.id, "otp_in": False}
                )
                return False
            except discord.HTTPException:
                return False

        elif actiontype == Actions.KICK:
            if not isinstance(target, discord.Member):
                return True
            if target == guild.owner:  # noqa: ignore
                return False
            elif target.top_role > guild.me.top_role:
                return False
            result = await self.strip_and_save(guild, target, case_id)
            await self.on_strip(guild, target, case_id, expires, result)
            if not result:
                return False
            try:
                await target.kick(reason=f"User Kicked [Report {case_id}'s Action!]")
                return True
            except discord.Forbidden:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id}, {"_id": guild.id, "otp_in": False}
                )
                return False
            except discord.HTTPException:
                return False

        elif actiontype == Actions.QUARANTINE:
            if not isinstance(target, discord.Member):
                return True
            if target == guild.owner:
                return False
            # first check quarantine role exists.
            quarantine_role = self.guild_config[guild.id]["quarantine_role"]
            if quarantine_role:
                quarantine_role = guild.get_role(quarantine_role)
                if not quarantine_role:
                    self.guild_config[guild.id]["otp_in"] = False
                    self.guild_config[guild.id]["quarantine_role"] = None
                    await self.bot.db.global_actions.upsert(
                        {"_id": guild.id},
                        {"_id": guild.id, "otp_in": False, "quarantine_role": None},
                    )
                    return False

                result = await self.strip_and_save(guild, target, case_id)
                await self.on_strip(guild, target, case_id, expires, result)
                if not result:
                    return False
                await target.add_roles(
                    quarantine_role,
                    reason=f"User Quarantined for {human_timedelta(expires, suffix=False, accuracy=4)}"
                    f" [Report {case_id}'s Action]!",
                )

        elif actiontype == Actions.MUTE:
            if not isinstance(target, discord.Member):
                return True
            if target == guild.owner:
                return False
            if target.guild_permissions.administrator:
                return False
            if not guild.me.guild_permissions.moderate_members:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id}, {"_id": guild.id, "otp_in": False}
                )
                return False
            result = await self.strip_and_save(guild, target, case_id)
            if not result:
                return False
            await target.timeout(
                expires,
                reason=f"User Muted for {human_timedelta(expires, suffix=False, accuracy=4)}"
                f" [Report {case_id}'s Action]!",
            )
        return True

    async def sanction(
        self,
        scope: ScopeTypes,
        category: str,
        subcategory: str,
        actiontype: Actions,
        target: int,
        case_id: int,
        guilds: Optional[List[discord.Guild]] = None,
        expires: Optional[datetime.datetime] = None,
    ) -> Dict[str, int] | Never:
        stats = {
            "success": 0,
            "failure": 0,
            "total": len(guilds) if guilds else 0,
            "guild_ids": [],  # Guilds where an action was successful
        }
        # guild_ids is used for appeal process.

        user = self.bot.get_user(target)
        if user:
            target = user
        else:
            try:
                target = await self.bot.fetch_user(target)
            except (discord.NotFound, discord.HTTPException):
                return stats

        # assert isinstance(target, discord.User)
        # This line seems to error so commented out

        if scope == ScopeTypes.GLOBAL:
            guilds = [
                g
                for g in self.bot.guilds
                if g.id in self.guild_config and self.guild_config[g.id]["otp_in"]
            ]
            stats["total"] = len(guilds)

        elif scope == ScopeTypes.MUTUAL:
            guilds = [
                g
                for g in self.bot.guilds
                if g.id in self.guild_config
                and self.guild_config[g.id]["otp_in"]
                and g.id in [tg.id for tg in target.mutual_guilds]
            ]
            stats["total"] = len(guilds)

        if len(guilds) < 1:
            return stats

        now = discord.utils.utcnow()

        for guild in guilds:
            result = await self.guild_sanction(
                guild, category, subcategory, actiontype, target, case_id, expires
            )
            if result is True:
                if expires or actiontype in [
                    Actions.BAN,
                    Actions.KICK,
                    Actions.QUARANTINE,
                ]:
                    # check if user already has a sanction with the same action-type and delete them
                    await self.bot.db.sanctions.delete(
                        {
                            "guild": guild.id,
                            "target": target.id,
                            "actiontype": actiontype.value,
                        }
                    )
                    # now insert the latest sanction for that sanction-type.
                    await self.bot.db.sanctions.insert(
                        {
                            "guild": guild.id,
                            "target": target.id,
                            "category": category,
                            "subcategory": subcategory,
                            "actiontype": actiontype.value,
                            "created": now,
                            "expires": expires,
                            "case_id": case_id,
                        }
                    )
                    # generate snowflake
                    if guild.id not in self.sanction_cache:
                        self.sanction_cache[guild.id] = {}
                    self.sanction_cache[guild.id][generate_snowflake()] = {
                        "target": target.id,
                        "actiontype": actiontype.value,
                        "created": now,
                        "expires": expires,
                        "case_id": case_id,
                        "category": category,
                        "subcategory": subcategory,
                    }
                    if expires:
                        await self.bot.reminder.create_timer(
                            expires.replace(tzinfo=datetime.timezone.utc),
                            "sanction",
                            guild=guild.id,
                            target=target.id,
                            actiontype=actiontype.value,
                            case_id=case_id,
                        )

                stats["success"] += 1
                stats["guild_ids"].append(guild.id)
            elif result is False:
                stats["failure"] += 1

            if result is not None and actiontype.value != 0:
                # send webhook logs to the guild
                await self.on_action(
                    guild,
                    target,
                    actiontype,
                    case_id,
                    category,
                    subcategory,
                    result,
                    expires,
                )
        # send the result to the author's DM
        if actiontype.value == 0:
            description = (
                f"Your account was reported in case number {case_id} to DDA!\n"
                f"We found you to not be involved / deserving of any actions as a consequence of this case!\n"
                f"**Note**: We are not discord, but a organisation on its platform that represents over {stats['total']:,} servers "
            )
        elif actiontype.value == 1:
            # warn
            description = (
                f"Your account was reported in case number {case_id} to DDA!\n"
                f"We have decided to **warn** you to not break our terms in servers that are represented by us!\n"
                f"**Note**: We are not discord, but a organisation on its platform that represents over {stats['total']:,} servers "
            )
        else:
            duration = None
            if expires:
                duration = human_timedelta(expires, suffix=False, accuracy=4)
            description = (
                f"Your account was reported in case number {case_id} to DDA!\n"
                f"The following actions were performed on your account: **{str(actiontype)}** in {stats['success']:,} Servers\n"
                + (f"**Duration**: {duration}\n" if duration else "")
                + f"[Appeal Here](https://discord.gg/vZVq7WX9SD)\n"
                f"**Note**: We are not discord, but a organisation on its platform that represents over {stats['total']:,} servers "
            )
        embed = discord.Embed(
            title="Discord Defence Association Notice",
            description=description,
            colour=discord.Colour.blurple(),
        )
        try:
            await target.send(embed=embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        if self.stats_channel:
            embed = discord.Embed(
                title=f"Stats for {target.name} (`{target.id}`)",
                description=(
                    "**Sanction Detail**:\n"
                    f"- **Case ID**: `{case_id}`\n"
                    f"- **DMED** {target.mention}: `{dm_sent}`\n"
                    f"- **Actions performed**: **{str(actiontype)}** in `{stats['success']:,}` Servers\n"
                    f"- **Expires**: {discord.utils.format_dt(expires, 'R') if expires else "N/A"}\n"
                    f"- **Server Stats**:\n<:elem_reply:1133489424437620766> **Success**: `{stats['success']:,}`\n<:elem_reply:1133489424437620766> **Failed**: `{stats['failure']:,}`\n<:elem_reply:1133489424437620766> **Total**: `{stats['total']:,}`"
                ),
                colour=discord.Colour.blurple(),
            )
            try:
                message = await self.stats_channel.send(
                    content="<@&1230306859718545478>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
                await message.publish()
            except Exception as e:
                print("global actions.sanctions", e)

        return stats

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if not self.bot.is_ready():
            await self.bot.wait_until_ready()
        if guild.id not in self.guild_config:
            return
        if not self.guild_config[guild.id]["otp_in"]:
            return
        if guild.id not in self.sanction_cache:
            return

        now = discord.utils.utcnow()
        sanction_cache = self.sanction_cache.get(guild.id, {})
        for _id in sanction_cache:
            found = sanction_cache[_id]
            if found["target"] != member.id:
                continue
            expires = found["expires"]
            if expires:
                if expires.replace(tzinfo=datetime.timezone.utc) <= now:
                    del self.sanction_cache[guild.id][_id]
                    return

            if found["actiontype"] != Actions.MUTE.value and member.is_timed_out():
                return

            result = await self.guild_sanction(
                guild,
                found["category"],
                found["subcategory"],
                Actions(found["actiontype"]),
                member,  # type: ignore
                found["case_id"],
                found["expires"],
            )
            await self.on_action(
                guild,
                member,  # type: ignore
                Actions(found["actiontype"]),
                found["case_id"],
                found["category"],
                found["subcategory"],
                result,
                found["expires"],
            )

    @commands.Cog.listener()
    async def on_sanction_timer_complete(self, timer: Timer) -> None:
        kws = timer.kwargs
        guild_id, target, actiontype, case_id = (
            kws["guild"],
            kws["target"],
            kws["actiontype"],
            kws["case_id"],
        )
        if not self.bot.is_ready():
            await self.bot.wait_until_ready()
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(target)

        if actiontype == Actions.BAN:
            result = False
            if guild.me.guild_permissions.ban_members:
                try:
                    ban_entry = await guild.fetch_ban(discord.Object(id=target))
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    pass
                else:
                    if f"[Report {case_id}'s Action]!" in ban_entry.reason:
                        try:
                            await guild.unban(
                                discord.Object(id=target),
                                reason=f"Ban Duration ended! Case ID: {case_id}",
                            )
                            result = True
                        except (
                            discord.Forbidden,
                            discord.NotFound,
                            discord.HTTPException,
                        ):
                            pass

            else:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id},
                    {
                        "_id": guild.id,
                        "otp_in": False,
                    },
                )

            await self.on_action_expiry(
                guild, discord.Object(id=target), actiontype, case_id, result
            )

        elif actiontype == Actions.QUARANTINE and member:
            result = False
            if guild.me.guild_permissions.manage_roles:  # noqa: ignore
                if guild.me.top_role > member.top_role:
                    quarantine_role = self.guild_config[guild.id]["quarantine_role"]
                    if quarantine_role:
                        quarantine_role = guild.get_role(quarantine_role)
                        if not quarantine_role:
                            self.guild_config[guild.id]["otp_in"] = False
                            self.guild_config[guild.id]["quarantine_role"] = None
                            await self.bot.db.global_actions.upsert(
                                {"_id": guild.id},
                                {
                                    "_id": guild.id,
                                    "otp_in": False,
                                    "quarantine_role": None,
                                },
                            )
                        else:
                            try:
                                await member.remove_roles(
                                    quarantine_role,
                                    reason=f"Quarantine Duration ended! Case ID: {case_id}",
                                )
                                result = True
                            except (discord.Forbidden, discord.HTTPException):
                                pass
                            restore_result = await self.restore_from_save(
                                guild, member, case_id=case_id
                            )
                            await self.on_restore(
                                guild, member, case_id, restore_result
                            )
            else:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id},
                    {"_id": guild.id, "otp_in": False, "quarantine_role": None},
                )

            await self.on_action_expiry(
                guild, member, Actions(actiontype), case_id, result
            )
        elif actiontype == Actions.MUTE and member:
            # when action-type.Mute we don't need to unmute as that is handled by discord
            # However we need to give their roles back!
            restore_result = await self.restore_from_save(
                guild, member, case_id=case_id
            )
            await self.on_restore(guild, member, case_id, restore_result)

        # delete the sanction

        await self.delete_sanction(guild, target, actiontype, case_id)

    async def delete_sanction(
        self, guild: discord.Guild, target: int, actiontype: str, case_id: int
    ):
        try:
            for _id in self.sanction_cache[guild.id]:
                found = self.sanction_cache[guild.id][_id]
                if (
                    found["target"] == target
                    and found["actiontype"] == actiontype
                    and found["case_id"] == case_id
                ):
                    del self.sanction_cache[guild.id][_id]
        except KeyError:
            pass

        await self.bot.db.sanctions.delete(
            {
                "guild": guild.id,
                "target": target,
                "actiontype": actiontype,
                "case_id": case_id,
            }
        )

    async def guild_appeal(
        self,
        guild: discord.Guild,
        target: discord.User,
        appealtype: AppealActions,
        category: str,
        subcategory: str,
        case_id: int,
    ) -> bool:
        member = guild.get_member(target.id)
        if member:
            target = member
        result = False
        if appealtype == AppealActions.UNBAN:
            if isinstance(target, discord.Member):
                result = True  # they are already unbanned
            elif guild.me.guild_permissions.ban_members:
                try:
                    ban_entry = await guild.fetch_ban(target)
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    pass
                else:
                    if (
                        not ban_entry.reason
                        == f"User Banned [Report {case_id}'s Action]!"
                    ):
                        return False
                    try:
                        await guild.unban(
                            target, reason=f"Appeal Accepted for case ID: {case_id}"
                        )
                        result = True
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass

            else:
                self.guild_config[guild.id]["otp_in"] = False
                await self.bot.db.global_actions.upsert(
                    {"_id": guild.id},
                    {
                        "_id": guild.id,
                        "otp_in": False,
                    },
                )

        elif appealtype == AppealActions.UNQUARANTINE:
            if isinstance(target, discord.Member):
                if guild.me.guild_permissions.manage_roles:  # noqa: ignore
                    if guild.me.top_role > member.top_role:
                        quarantine_role = self.guild_config[guild.id]["quarantine_role"]
                        if quarantine_role:
                            quarantine_role = guild.get_role(quarantine_role)
                            if not quarantine_role:
                                self.guild_config[guild.id]["otp_in"] = False
                                self.guild_config[guild.id]["quarantine_role"] = None
                                await self.bot.db.global_actions.upsert(
                                    {"_id": guild.id},
                                    {
                                        "_id": guild.id,
                                        "otp_in": False,
                                        "quarantine_role": None,
                                    },
                                )
                            else:
                                try:
                                    await member.remove_roles(
                                        quarantine_role,
                                        reason=f"Appeal Accepted for Case ID: {case_id}",
                                    )
                                    result = True
                                except (discord.Forbidden, discord.HTTPException):
                                    pass
                                restore_result = await self.restore_from_save(
                                    guild, member, case_id=case_id
                                )
                                await self.on_restore(
                                    guild, member, case_id, restore_result
                                )
                else:
                    self.guild_config[guild.id]["otp_in"] = False
                    await self.bot.db.global_actions.upsert(
                        {"_id": guild.id},
                        {"_id": guild.id, "otp_in": False, "quarantine_role": None},
                    )

        elif appealtype == AppealActions.UNMUTE:
            if isinstance(target, discord.Member):
                if not target.is_timed_out():
                    return True
                if guild.me.guild_permissions.moderate_members:
                    try:
                        await member.edit(timed_out_until=None)
                        result = True
                        restore_result = await self.restore_from_save(
                            guild, target, case_id=case_id
                        )
                        await self.on_restore(guild, member, case_id, restore_result)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        await self.on_appeal(
            guild, target, appealtype, category, subcategory, case_id, result
        )

        return result

    async def appeal(
        self,
        target: int,
        case_id: int,
        actiontype: Actions,
        appealtype: AppealActions,
        category: str,
        subcategory: str,
        guilds: List[discord.Guild],
    ) -> Dict[str, int] | Never:
        stats = {
            "success": 0,
            "failure": 0,
            "total": len(guilds),
        }
        # guild_ids is used for appeal process.

        user = self.bot.get_user(target)
        if user:
            target = user
        else:
            try:
                target = await self.bot.fetch_user(target)
            except (discord.NotFound, discord.HTTPException):
                return stats

        if len(guilds) < 1:
            return stats

        for guild in guilds:
            result = await self.guild_appeal(
                guild, target, appealtype, category, subcategory, case_id
            )

            # await self.bot.db.sanctions.delete({
            #     "guild": guild.id,
            #     "target": target.id,
            #     "actiontype": actiontype.value
            # })

            await self.delete_sanction(guild, target.id, str(actiontype), case_id)

            stats["success"] += 1
            if result:
                stats["success"] += 1
            elif result is False:
                stats["failure"] += 1
            if result is not None:
                # send webhook logs to the guild
                await self.on_appeal(
                    guild,
                    target,
                    appealtype,
                    category,
                    subcategory,
                    case_id,
                    result,
                )

        return stats
