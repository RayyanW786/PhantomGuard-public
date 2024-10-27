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

import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

import discord
from discord.app_commands import describe, guilds
from discord.ext import commands

from ..global_actions import Actions, ScopeTypes

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.reminder import Timer
    from utils.context import Context

from logging import getLogger

from discord.ext.menus import ListPageSource

from utils.checks import is_botmod
from utils.paginator import RoboPages

from .converters import GuildsConverter, UsersConverter
from .helper import ReportManager
from .polling import Polling
from .views import BasicReportView, DraftView

log = getLogger(__name__)


class Reports(commands.Cog):
    def __init__(self, bot: PhantomGuard):
        self.bot: PhantomGuard = bot
        self.polling: Polling = Polling(self, bot)
        self.reports: ReportManager = ReportManager(bot)

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="dda_report", id=1239551035853246567)

    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.hybrid_group(name="report", invoke_without_command=True)
    async def report(self, ctx: Context):
        await ctx.send_help("report")

    @describe(
        user="The user you want to report",
        brief="A quick summary of the report 125 character limit!",
        category="The main category the report fits into",
        subcategory="The sub category the report fits into",
        server_id="The server that this happened in, if multiple separate with space e.g 1 2 ...",
        anonymous="If you would like to remain anonymous. [You can still be bot banned for troll reports]!",
    )
    @report.command(name="single")
    async def report_single(
        self,
        ctx: Context,
        user: discord.Member | discord.User,
        brief_description: str,
        category: str,
        subcategory: str,
        anonymous: bool = False,
        server_ids: Optional[GuildsConverter] = None,
    ):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()

        guild = ctx.bot.get_guild(1228685085944053882)
        if ctx.author.id not in [m.id for m in guild.members]:
            return await ctx.reply(
                "Only [DDA members](https://discord.gg/APGVPvB8k8) can use /report",
                ephemeral=True,
            )

        if server_ids:
            server_ids = [s.id for s in server_ids]

        await self.reports.create_draft(
            ctx,
            [user.id],
            brief_description[:250],
            category.lower(),
            subcategory.lower(),
            anonymous,
            server_ids,
        )

    @report.command(name="view")
    async def report_view(self, ctx: Context, case_id: int):
        """View a report"""
        data = await self.bot.db.reports.find({"_id": case_id})
        if not data:
            return await ctx.reply("This report does not exist.", ephemeral=True)

        if data["subcategory"].lower() == "nsfw":
            if not ctx.channel.is_nsfw():
                return await ctx.reply(
                    "This report is marked as NSFW.\nYou can only view this in channels marked as NSFW",
                    ephemeral=True,
                )

        embed = discord.Embed(
            title=f"Report ID: {data['_id']}",
            description=(
                f"**Reported by**: `{data['reported_by'] if not data['is_anonymous'] else 'anonymous'}`\n"
                f"**Reference**: `{data['_id']}`\n"
                f"**Report Type**: `{data['addressing_type']}`\n"
                f"**Category**: `{data['category']}`\n**Subcategory**: `{data['subcategory']}`\n"
                f"**Users Reported**: {', '.join(map(str, data['reported_users']))}\n"
                f"**Associated Servers**: {', '.join(map(str, (data['associated_servers']) or ['None'])).strip()}\n"
            ),
            colour=discord.Colour.blurple(),
        )
        # votes_for = [self.bot.get_user(u) for u in data['polling']['users']['for']]
        # votes_for = [f"`{u.name if u else u}`" for u in votes_for]

        embed.add_field(
            name="Votes For",
            value=int(data["polling"]["points"]["for"]),
            # value="\n".join(votes_for)
        )
        await ctx.reply(embed=embed, view=BasicReportView(ctx, data), ephemeral=True)

    @report.command(name="for")
    async def report_for(self, ctx: Context, member: discord.Member):
        """Lists all the reports that resulted in a sanction that isn't None for the given user"""
        reports = await self.bot.db.reports.find_many(
            {"reported_users": {"$all": [member.id]}}
        )
        _ids = [rep["_id"] for rep in reports]

        def format_pages(menu, entries):
            return discord.Embed(
                title="Report Paginator", description=ctx.humanize_list(entries)
            )

        source = ListPageSource(list(map(str, _ids)), per_page=10)
        source.format_page = format_pages
        p = RoboPages(
            source,
            author=ctx.author,
        )
        await p.start_with_ctx(ctx=ctx, ephemeral=True if ctx.interaction else False)

    @describe(
        user_ids="The users you want to report",
        brief="A quick summary of the report 250 character limit!",
        category="The main category the report fits into",
        subcategory="The sub category the report fits into",
        server_id="The server that this happened in, if multiple separate with space e.g 1 2 ...",
        anonymous="If you would like to remain anonymous. [You can still be bot banned for troll reports]!",
    )
    @report.command("many")
    async def report_many(
        self,
        ctx: Context,
        user_ids: Optional[UsersConverter],
        brief_description: str,
        category: str,
        subcategory: str,
        anonymous: bool = False,
        server_ids: Optional[GuildsConverter] = None,
    ):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        guild = ctx.bot.get_guild(1228685085944053882)
        if ctx.author.id not in [m.id for m in guild.members]:
            return await ctx.reply("Only DDA members can use /report", ephemeral=True)

        user_ids: List[int]
        await self.reports.create_draft(
            ctx,
            [u.id for u in user_ids],
            brief_description[:125],
            category.lower(),
            subcategory.lower(),
            anonymous,
            server_ids,
        )

    @report.command(name="attach")
    async def report_attach(
        self,
        ctx: Context,
        draft_id: int,
        attachment_1: discord.Attachment,
        attachment_2: Optional[discord.Attachment],
        attachment_3: Optional[discord.Attachment],
        attachment_4: Optional[discord.Attachment],
        attachment_5: Optional[discord.Attachment],
        attachment_6: Optional[discord.Attachment],
        attachment_7: Optional[discord.Attachment],
        attachment_8: Optional[discord.Attachment],
        attachment_9: Optional[discord.Attachment],
        attachment_10: Optional[discord.Attachment],
        attachment_11: Optional[discord.Attachment],
        attachment_12: Optional[discord.Attachment],
        attachment_13: Optional[discord.Attachment],
        attachment_14: Optional[discord.Attachment],
        attachment_15: Optional[discord.Attachment],
    ):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        guild = ctx.bot.get_guild(1228685085944053882)
        if ctx.author.id not in [m.id for m in guild.members]:
            return await ctx.reply("Only DDA members can use /report", ephemeral=True)

        await self.reports.attach_proof(
            ctx,
            draft_id,
            attachments=[
                attach
                for attach in [
                    attachment_1,
                    attachment_2,
                    attachment_3,
                    attachment_4,
                    attachment_5,
                    attachment_6,
                    attachment_7,
                    attachment_8,
                    attachment_9,
                    attachment_10,
                    attachment_11,
                    attachment_12,
                    attachment_13,
                    attachment_14,
                    attachment_15,
                ]
                if attach
            ],
            _type="draft",
        )

    @report.group(name="draft", invoke_without_command=True)
    async def draft(self, ctx: Context):
        await ctx.send_help("report draft")

    @describe(
        case_id="The draft's case ID. Use /report draft list to get a list of drafts.",
    )
    @draft.command(name="select")
    async def draft_select(self, ctx: Context, case_id: int):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        draft = await self.bot.db.drafts.find(
            {
                "_id": case_id,
                "owner": ctx.author.id,
            }
        )
        if not draft:
            await ctx.send("Draft not found!", ephemeral=True)
            return
        description = (
            f"**Reported User**: {' '.join(map(str, draft['reported_users']))}\n"
            f"**Category**: {draft['category']}\n**Subcategory**: {draft['subcategory']}\n"
            f"**Anonymous**: {draft['is_anonymous']}\n"
            f"**Servers Involved**: {' '.join(map(str, (draft['associated_servers']) or ['None'])).strip()}"
        )
        embed = discord.Embed(
            title=f"Report Draft {case_id}",
            description=description,
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Brief Description", value=draft["brief_description"])
        view = DraftView(ctx, draft)
        message = await ctx.send(embed=embed, view=view, ephemeral=True)
        view.message = message

    @draft.command(name="list")
    async def draft_list(self, ctx: Context):
        drafts = await self.bot.db.drafts.find_many(
            {
                "owner": ctx.author.id,
            }
        )
        if not drafts:
            await ctx.send("You don't have any report drafts", ephemeral=True)
            return

        pages: List[discord.Embed] = []
        for data in drafts:
            description = (
                f"**Reported Users**: {' '.join(map(str, data['reported_users']))}\n"
                f"**Category**: {data['category']}\n**Sub category**: {data['subcategory']}\n"
                f"**Anonymous**: {data['is_anonymous']}\n"
                f"**Servers Involved**: {' '.join(map(str, (data['associated_servers']) or ['None'])).strip()}"
            )
            embed = discord.Embed(
                title=f"Draft ID `{data['_id']}`",
                description=description,
                colour=discord.Colour.blurple(),
            )
            embed.add_field(name="Brief Description", value=data["brief_description"])
            pages.append(embed)

        def format_pages(menu, entries):
            return entries

        source = ListPageSource(pages, per_page=1)
        source.format_page = format_pages
        p = RoboPages(
            source,
            author=ctx.author,
        )
        await p.start_with_ctx(ctx=ctx, ephemeral=True if ctx.interaction else False)

    @describe(
        case_id="The draft's case ID. Use /report draft list to get a list of drafts.",
    )
    @draft.command(name="delete")
    async def draft_delete(self, ctx: Context, case_id: int):
        deleted = await self.bot.db.drafts.delete(
            {
                "_id": case_id,
                "owner": ctx.author.id,
            }
        )
        if deleted:
            await ctx.reply("Draft deleted", ephemeral=True)
        else:
            await ctx.reply("Draft not found", ephemeral=True)

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @commands.hybrid_group(name="polling", invoke_without_command=True)
    async def polling(self, ctx: Context):
        await ctx.send_help("polling")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @polling.command(name="attach")
    async def polling_attach(
        self,
        ctx: Context,
        poll_id: int,
        message: discord.Message,
        attachment_1: Optional[discord.Attachment],
        attachment_2: Optional[discord.Attachment],
        attachment_3: Optional[discord.Attachment],
        attachment_4: Optional[discord.Attachment],
        attachment_5: Optional[discord.Attachment],
        attachment_6: Optional[discord.Attachment],
        attachment_7: Optional[discord.Attachment],
        attachment_8: Optional[discord.Attachment],
        attachment_9: Optional[discord.Attachment],
        attachment_10: Optional[discord.Attachment],
        attachment_11: Optional[discord.Attachment],
        attachment_12: Optional[discord.Attachment],
        attachment_13: Optional[discord.Attachment],
        attachment_14: Optional[discord.Attachment],
        attachment_15: Optional[discord.Attachment],
    ):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        if message.author.id != self.bot.user.id:
            return await ctx.reply(
                "Invalid Message ID [invalid author]", ephemeral=True
            )
        if (
            message.channel.id != self.polling.polling_channel.id
            and message.channel.id != self.polling.nsfw_channel
        ):
            return await ctx.reply(
                "Invalid Message ID [invalid channel]", ephemeral=True
            )
        if not message.embeds:
            return await ctx.reply("Invalid Message ID [no embeds]", ephemeral=True)
        if f"**Reference**: {poll_id}" not in message.embeds[0].description:
            return await ctx.reply("Invalid Message ID [Poll ID]", ephemeral=True)

        await self.reports.attach_proof(
            ctx,
            poll_id,
            attachments=[
                attach
                for attach in [
                    attachment_1,
                    attachment_2,
                    attachment_3,
                    attachment_4,
                    attachment_5,
                    attachment_6,
                    attachment_7,
                    attachment_8,
                    attachment_9,
                    attachment_10,
                    attachment_11,
                    attachment_12,
                    attachment_13,
                    attachment_14,
                    attachment_15,
                ]
                if attach
            ],
            _type="poll",
            message=message,
        )

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @polling.command(name="start")
    async def polling_start(self, ctx: Context, case_id: int):
        await ctx.defer(ephemeral=True)
        data = await self.bot.db.pollings.find({"_id": case_id, "type": "queued"})
        if data:
            result = await self.polling.create_draft_polling(data, True)
            await ctx.reply(
                "Polling Successful" if result else "Polling Failed", ephemeral=True
            )
        else:
            await ctx.reply("Poll not found!")

    @guilds(discord.Object(id=1228685085944053882))
    @is_botmod()
    @polling.command(name="queue")
    async def polling_queue(self, ctx: Context):
        polling_queue = await self.bot.db.pollings.find_many({"type": "queued"})
        if not polling_queue:
            return await ctx.reply("no reports are queued for polling", ephemeral=True)

        pages: List[discord.Embed] = []
        for data in polling_queue:
            embed = discord.Embed(
                title=f"Polling ID: {data['_id']}",
                description=(
                    f"**Reported by**: {data['owner'] if not data['is_anonymous'] else 'anonymous'}\n"
                    f"**Reference**: {data['_id']}\n"
                    f"**Category**: {data['category']}\n**Subcategory**: {data['subcategory']}\n"
                    f"**Users Reported**: {', '.join(map(str, data['reported_users']))}\n"
                    f"**Associated Servers**: {' '.join(map(str, (data['associated_servers']) or ['None'])).strip()}\n"
                ),
                colour=discord.Colour.blurple(),
            )
            embed.add_field(name="Brief Description", value=data["brief_description"])
            pages.append(embed)

        def format_pages(menu, entries):
            return entries

        source = ListPageSource(pages, per_page=1)
        source.format_page = format_pages
        p = RoboPages(
            source,
            author=ctx.author,
        )
        await p.start_with_ctx(ctx=ctx, ephemeral=True if ctx.interaction else False)

    @commands.Cog.listener()
    async def on_poll_timer_complete(self, timer: Timer):
        # check the option with the most votes
        _id = timer.kwargs["data"]["_id"]
        data = await self.bot.db.pollings.find({"_id": _id})
        deleted = await self.bot.db.pollings.delete({"_id": _id})
        if not deleted or not data:
            return
        most_votes = None
        for idx, option in enumerate(data["options"]):
            if not most_votes:
                most_votes = option
                continue
            if (
                option["polling"]["points"]["for"]
                > most_votes["polling"]["points"]["for"]
            ):
                most_votes = option
        if not most_votes or most_votes["polling"]["points"]["for"] < 5:
            await self.polling.to_queue(data)
            return
        if not self.polling.global_actions:
            await self.polling.to_queue(data)
            return
        stats: Dict[str, Dict] = {}
        report_id = await self.reports.get_id("report")

        for sanction in most_votes["sanctions"]:
            scope = None
            if sanction["scope"] == "global":
                scope = ScopeTypes.GLOBAL
            elif sanction["scope"] == "mutual":
                scope = ScopeTypes.MUTUAL
            elif sanction["scope"] == "targeted":
                scope = ScopeTypes.TARGETED

            action = Actions.from_str(sanction["action"])
            guilds = None
            if scope == ScopeTypes.TARGETED:
                guilds = sanction["guilds"]
            for user in sanction["users"]:
                expires: Optional[float] = sanction["expires"]
                if expires:
                    expires: datetime.datetime = (
                        discord.utils.utcnow() + datetime.timedelta(seconds=expires)
                    )
                local_stats = await self.polling.global_actions.sanction(
                    scope,
                    most_votes["category"],
                    most_votes["subcategory"],
                    action,
                    user,
                    report_id,
                    guilds,
                    expires,
                )
                stats[str(user)] = local_stats

        await self.bot.db.reports.insert(
            {
                "_id": report_id,
                "reported_users": data["reported_users"],
                "associated_servers": data["associated_servers"],
                "category": data["category"],
                "subcategory": data["subcategory"],
                "attachments": most_votes["attachments"],
                "addressing_type": most_votes["addressing_type"],
                "brief_description": None,  # todo: in the future allow mods to set their own brief + long desc
                "long_description": None,
                "reported_by": data["owner"],
                "is_anonymous": data["is_anonymous"],
                "sanctions": most_votes["sanctions"],
                "created_at": data["created_at"],
                "pushed_at": discord.utils.utcnow(),
                "polling": most_votes["polling"],
                "stats": stats,
            }
        )

    @commands.Cog.listener()
    async def on_draft_expiry_timer_complete(self, timer: Timer) -> None:
        data = timer.kwargs["data"]
        await self.bot.db.drafts.delete(
            {
                "_id": data["_id"],
            }
        )
