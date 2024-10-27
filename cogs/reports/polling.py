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
from typing import TYPE_CHECKING, Dict, Optional, Set

import discord

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.global_actions import GlobalActions
    from cogs.reports import Reports

from .views import VerifyReportView


class Polling:
    def __init__(self, cog: Reports, bot: PhantomGuard) -> None:
        self.cog: Reports = cog
        self.bot: PhantomGuard = bot
        self.polling_channel: Optional[discord.TextChannel] = None
        self.nsfw_channel: Optional[discord.TextChannel] = None
        self.global_actions: Optional[GlobalActions] = None
        asyncio.create_task(self.setup())

    async def setup(self) -> None:
        await self.bot.wait_until_ready()
        self.polling_channel: Optional[discord.TextChannel] = self.bot.get_channel(
            1233789181419851776
        )
        # self.polling_channel = self.bot.get_channel(1241769546197630996)  # demo channel
        self.nsfw_channel: Optional[discord.TextChannel] = self.bot.get_channel(
            1242117277445390469
        )
        gas_cog = self.bot.get_cog("GlobalActions")
        if gas_cog:
            gas_cog: GlobalActions
            self.global_actions = gas_cog

    async def create_draft_polling(
        self, draft_data, from_polling: bool = False
    ) -> Optional[bool]:
        channel_ref = (
            self.nsfw_channel
            if draft_data["subcategory"].lower() == "nsfw"
            else self.polling_channel
        )
        if channel_ref is None:
            return None
        to_insert = {
            "_id": draft_data["_id"],
            "attachments": draft_data["attachments"],
            "reported_users": draft_data["reported_users"],
            "associated_servers": draft_data["associated_servers"],
            "category": draft_data["category"],
            "subcategory": draft_data["subcategory"],
            "brief_description": draft_data["brief_description"],
            "long_description": draft_data["long_description"],
            "owner": draft_data["owner"],
            "is_anonymous": draft_data["is_anonymous"],
            "type": ("queued" if channel_ref is None else "polled"),
            "options": [],
            "created_at": discord.utils.utcnow(),
            "expires": discord.utils.utcnow() + datetime.timedelta(days=1),
            "stage": 1,  # Stage 1: Verify, Stage 2: Options
            "stage1_vote": {
                "points_for": 0,
                "points_against": 0,
                "users_for": [],
                "users_against": [],
            },
        }
        deleted = await self.bot.db.drafts.delete(
            {
                "_id": draft_data["_id"],
                "owner": draft_data["owner"],
            }
        )
        if not deleted and not from_polling:
            return False
        if not self.bot.reminder:
            return False
        if not from_polling:
            await self.bot.db.pollings.insert(to_insert)
        else:
            await self.bot.db.pollings.update(
                {"_id": draft_data["_id"]},
                {
                    "type": ("queued" if channel_ref is None else "polled"),
                    "expires": discord.utils.utcnow() + datetime.timedelta(days=1),
                },
            )
        await self.bot.reminder.create_timer(
            discord.utils.utcnow() + datetime.timedelta(days=1), "poll", data=to_insert
        )
        await self.send_poll(to_insert)
        return True

    async def send_poll(self, data: Dict) -> None:
        channel_ref = (
            self.nsfw_channel
            if data["subcategory"].lower() == "nsfw"
            else self.polling_channel
        )
        view = VerifyReportView(self.bot, data)
        embed = discord.Embed(
            description=(
                f"**Reported by**: {data['owner'] if not data['is_anonymous'] else 'anonymous'}\n"
                f"**Reference**: {data['_id']}\n"
                f"**Category**: {data['category']}\n**Subcategory**: {data['subcategory']}\n"
                f"**Users Reported**: {', '.join(map(str, data['reported_users']))}\n"
                f"**Associated Servers**: {', '.join(map(str, (data['associated_servers'] or ["None"])))}\n"
                f"**Poll Expires** {discord.utils.format_dt(data['expires'])}"
            ),
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Brief Description", value=data["brief_description"])
        # demo_mention = [
        #     f"<@{men}>" for men in
        #     [
        #         id,
        #         ...
        #     ]
        # ]

        message = await channel_ref.send(
            # ", ".join(demo_mention),
            "@everyone",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=True, users=True),
        )
        thread = await message.create_thread(
            name=f"Poll {data['_id']}",
            auto_archive_duration=1440,
            reason="Polling discussion",
        )
        to_send = (
            (f"Reported By: <@{data['owner']}>\n" if not data["is_anonymous"] else "")
            + f"Users Reported: {', '.join(['<@' + str(user) + '>' for user in data['reported_users']])}"
        )
        await thread.send(to_send)

    async def to_queue(self, data: Dict):
        total_engagement: Set[int] = set()
        for idx, option in enumerate(data["options"]):
            for user in option["polling"]["users"]["for"]:
                total_engagement.add(user)
            for user in option["polling"]["users"]["against"]:
                total_engagement.add(user)
            if len(total_engagement) > 5:
                break
        if len(total_engagement) < 5:
            data["type"] = "queued"
            await self.bot.db.pollings.insert(data)
        else:
            await self.bot.db.pollings.delete(
                {
                    "_id": data["_id"],
                }
            )
