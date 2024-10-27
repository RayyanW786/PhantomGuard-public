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
import os
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Union,
)

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from utils.activities import gen_activities
from utils.blacklist import Blacklist
from utils.context import Context
from utils.mongo import MongoManager
from utils.simple_cache import AsyncTimedCache

if TYPE_CHECKING:
    from cogs.reminder import Reminder

from cogs.reports.views import PollingView, VerifyReportView

load_dotenv()

log = logging.getLogger(__name__)

description = """
A bot made to protect users and Servers
"""

# major, minor, micro
version_info = (1, 0, 0)

initial_extensions = [
    "jishaku",
    "cogs.admin",
    "cogs.configuration",
    "cogs.errors",
    "cogs.global_actions",
    "cogs.owner",
    "cogs.registration",
    "cogs.reports",
    "cogs.reminder",
    "cogs.miscellaneous",
    "cogs.impersonation",
    "cogs.fun",
]
excluded_extensions = []
intents = discord.Intents.default()
intents.members = True
# intents.message_content = True


class PhantomGuard(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            command_prefix=self.get_prefix,
            description=description,
            chunk_guilds_at_startup=True,
            heartbeat_timeout=150.0,
            allowed_mentions=discord.AllowedMentions.none(),
            intents=intents,
            # enable_debug_events = True,
            shard_count=1,
            shard_ids=[0],
            status=self.change_activity.start(),
        )
        self.version_info: tuple[int, int, int] = version_info
        self.__version__: str = ".".join(str(self.version_info))
        self.maintenance_mode: bool = False

    async def setup_hook(self) -> None:
        self.registering_guilds: List[int] = []
        self.session = aiohttp.ClientSession()
        self.owner_ids: List[int] = [613752401878450176, 921020428791742515]
        # self.config: Dict[str, Dict] = {"bypassed": {}, "disabled": {}}
        # # this code no longer is needed as it is shifted to redis.
        # self.main_config: Dict[int, dict] = {}
        self.admins: List[int] = []
        self.mods: List[int] = []
        self.admins.extend(self.owner_ids)

        self.bans: Dict[str, Set] = {"guild": set(), "user": set()}
        self.ablc_cache = AsyncTimedCache(loop=self.loop)

        # database setup
        self.db: MongoManager = MongoManager(
            os.getenv("MONGO"), database_name="phantom"
        )
        try:
            self.db.get_current_documents()
        except Exception:
            raise RuntimeError("Db failed to connect.")

        for extension in [
            ext for ext in initial_extensions if ext not in excluded_extensions
        ]:
            try:
                await self.load_extension(extension)
                log.info("Loaded extension %s.", extension)
            except Exception:
                log.exception("Failed to load extension %s.", extension)
        try:
            self.blacklist: Blacklist = Blacklist(self)
            await self.blacklist.setup()
            log.info("Blacklist initialized.")
        except Exception:
            raise RuntimeError("Blacklist failed to initialize, check db connection.")

        self.tree.interaction_check = self.interaction_check

        for admin in await self.db.admins.get_all():
            self.admins.append(admin["_id"])

        for mod in await self.db.mods.get_all():
            self.mods.append(mod["_id"])

        log.info("Populating DB cache")

        # this code no longer is needed as it is shifted to redis.

        asyncio.create_task(self.cache_empty_guilds())

        log.info(
            "DB cache fully populated, access it via: `{bot.main_config}` / `{bot.config}` (for command bypass list)"
        )

        polled_reports = await self.db.pollings.find_many(
            {
                "type": "polled",
            }
        )
        for polled_report in polled_reports:
            if polled_report["type"] != "polled":
                continue
            if (
                polled_report["expires"].replace(tzinfo=datetime.timezone.utc)
                <= discord.utils.utcnow()
            ):

                class TimerProxy:
                    def __init__(self, data):
                        self.kwargs: Dict = {"data": data}

                self.dispatch("poll_timer_complete", TimerProxy(polled_report))
                continue
            stage = polled_report["stage"]
            if stage == 1:
                self.add_view(
                    VerifyReportView(
                        self,
                        polled_report,
                    )
                )
            elif stage == 2:
                self.add_view(PollingView(self, polled_report))

    # async def cache_empty_guilds(self):
    # [omitted as cache was shifted to redis in latest build]

    @property
    def owners(self) -> List[discord.User]:
        users = []
        for owner_id in self.owner_ids:
            users.append(self.get_user(owner_id))
        return users

    @tasks.loop(seconds=600)
    async def change_activity(self):
        """Changes the bot's activity every 600 seconds"""

        await self.change_presence(
            activity=gen_activities(self), status=discord.Status.dnd
        )

    @change_activity.before_loop
    async def before_change_activity(self):
        await self.wait_until_ready()

    async def query_member_named(
        self, guild: discord.Guild, argument: str, *, cache: bool = False
    ) -> Optional[discord.Member]:
        """Queries a member by their name, name + discrim, or nickname.

        Parameters
        ------------
        guild: Guild
            The guild to query the member in.
        argument: str
            The name, nickname, or name + discrim combo to check.
        cache: bool
            Whether to cache the results of the query.

        Returns
        ---------
        Optional[Member]
            The member matching the query or None if not found.
        """
        if len(argument) > 5 and argument[-5] == "#":
            username, _, discriminator = argument.rpartition(
                "#"
            )  # TODO: change due to removal of discriminator
            members = await guild.query_members(username, limit=100, cache=cache)
            return discord.utils.get(
                members, name=username, discriminator=discriminator
            )
        else:
            members = await guild.query_members(argument, limit=100, cache=cache)
            return discord.utils.find(
                lambda m: m.name == argument or m.nick == argument, members
            )

    async def get_or_fetch_guild(self, guild_id: int) -> Optional[discord.Guild]:
        """Looks up the given guild in cache or fetches if not found.

        Parameters
        -----------
        guild_id: int
            The id of the guild to look for.

        Returns
        ---------
        Optional[Guild]
            The guild or None if not found.
        """

        guild = self.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.fetch_guild(guild_id)
            except (discord.Forbidden, discord.HTTPException):
                return None
        return guild

    async def get_or_fetch_member(
        self, guild: discord.Guild, member_id: int
    ) -> Optional[discord.Member]:
        """Looks up a member in cache or fetches if not found.

        Parameters
        -----------
        guild: Guild
            The guild to look in.
        member_id: int
            The member ID to search for.

        Returns
        ---------
        Optional[Member]
            The member or None if not found.
        """

        member = guild.get_member(member_id)
        if member is not None:
            return member

        shard: discord.ShardInfo = self.get_shard(guild.shard_id)  # type: ignore  # will never be None
        if shard.is_ws_ratelimited():
            try:
                member = await guild.fetch_member(member_id)
            except discord.HTTPException:
                return None
            else:
                return member

        members = await guild.query_members(limit=1, user_ids=[member_id], cache=True)
        if not members:
            return None
        return members[0]

    async def resolve_member_ids(
        self, guild: discord.Guild, member_ids: Iterable[int]
    ) -> AsyncIterator[discord.Member]:
        """Bulk resolves member IDs to member instances, if possible.

        Members that can't be resolved are discarded from the list.

        This is done lazily using an asynchronous iterator.

        Note that the order of the resolved members is not the same as the input.

        Parameters
        -----------
        guild: Guild
            The guild to resolve from.
        member_ids: Iterable[int]
            An iterable of member IDs.

        Yields
        --------
        Member
            The resolved members.
        """

        needs_resolution = []
        for member_id in member_ids:
            member = guild.get_member(member_id)
            if member is not None:
                yield member
            else:
                needs_resolution.append(member_id)

        total_need_resolution = len(needs_resolution)
        if total_need_resolution == 1:
            shard: discord.ShardInfo = self.get_shard(guild.shard_id)  # type: ignore  # will never be None
            if shard.is_ws_ratelimited():
                try:
                    member = await guild.fetch_member(needs_resolution[0])
                except discord.HTTPException:
                    pass
                else:
                    yield member
            else:
                members = await guild.query_members(
                    limit=1, user_ids=needs_resolution, cache=True
                )
                if members:
                    yield members[0]
        elif total_need_resolution <= 100:
            # Only a single resolution call needed here
            resolved = await guild.query_members(
                limit=100, user_ids=needs_resolution, cache=True
            )
            for member in resolved:
                yield member
        else:
            # We need to chunk these in bits of 100...
            for index in range(0, total_need_resolution, 100):
                to_resolve = needs_resolution[index : index + 100]
                members = await guild.query_members(
                    limit=100, user_ids=to_resolve, cache=True
                )
                for member in members:
                    yield member

    async def on_ready(self) -> None:
        if not hasattr(self, "starttime"):
            self.starttime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def get_context(
        self, origin: Union[discord.Interaction, discord.Message], /, *, cls=Context
    ) -> Context:
        return await super().get_context(origin, cls=cls)

    async def process_commands(self, message: discord.Message) -> None:
        ctx: Context = await self.get_context(message)

        if ctx.guild:
            author_id = ctx.author.id
            guild_id = ctx.guild.id

            if (
                self.maintenance_mode and ctx.command
            ):  # this make sures one of the bot's cmd was run, inorder to not
                # send warnings every other msg/
                if author_id not in self.owner_ids:
                    await ctx.send_embed(
                        "info", "Phantom Guard is currently on maintenance mode.", True
                    )
                    return
            if author_id not in self.owner_ids:
                if author_id in self.blacklist.users:
                    return
                elif guild_id in self.blacklist.guilds:
                    return

            if (
                message.raw_mentions and message.guild.me.id in message.raw_mentions
            ) and (
                len(message.content) == len(message.guild.me.mention)
                and message.content == message.guild.me.mention
            ):
                try:
                    await ctx.send_embed(
                        "info", f"My current prefix here is: {message.guild.me.mention}"
                    )
                except discord.errors.Forbidden:
                    pass
                return

        await self.invoke(ctx)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user:
            await interaction.response.send_message(
                "ERROR: Unknown Interaction Author", ephemeral=True
            )
            return False

        if interaction.user.id in self.owner_ids:
            return True

        if interaction.user.id in self.blacklist.users:
            await interaction.response.send_message(
                "You are bot banned!", ephemeral=True
            )
            return False

        if interaction.guild and interaction.guild.id in self.blacklist.guilds:
            await interaction.response.send_message(
                f"The server {interaction.guild.name} is bot banned!", ephemeral=True
            )
            return False

        if self.maintenance_mode:
            await interaction.response.send_message(
                "Bot is in maintenance mode!", ephemeral=True
            )
            return False

        return True

    def get_avatar_url_for(
        self, member: Union[discord.Member, discord.User], display=False
    ) -> str:
        if display and member.display_avatar:
            return member.display_avatar.url
        return (
            member.avatar.url
            if member.avatar is not None
            else member.default_avatar.url
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        await self.process_commands(message)

    async def get_prefix(self, message: discord.Message) -> str:
        prefix = ["p!", "P!"]
        return commands.when_mentioned_or(*prefix)(self, message)

    async def close(self) -> None:
        log.info("Shutdown initiated, cleaning up...")
        await self.session.close()
        return await super().close()

    async def start(self) -> None:
        return await super().start(
            os.getenv("DEV_TOKEN" if os.name == "nt" else "TOKEN", os.getenv("TOKEN")),
            reconnect=True,
        )

    @property
    def reminder(self) -> Optional[Reminder]:
        return self.get_cog("Reminder")
