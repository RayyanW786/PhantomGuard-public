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

# import gzip | [lossless] Will be using One compression algo only
import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import discord
from PIL import Image  # Lossy compression

from .views import PollingView, VerifyReportView

if TYPE_CHECKING:
    from discord import Attachment

    from bot import PhantomGuard
    from cogs.global_actions import GlobalActions
    from utils.context import Context

from .views import DraftView


class ReportManager:
    def __init__(self, bot: PhantomGuard):
        self.bot: PhantomGuard = bot

    async def get_id(self, collection: Literal["draft", "report"]) -> int:
        data = await self.bot.db.counters.find({"_id": "collection_ids"})
        if data is None:
            await self.bot.db.counters.insert(
                {"_id": "collection_ids", "draft": 0, "report": 0}
            )
            return 0

        new = data[collection] + 1
        await self.bot.db.counters.update(
            {"_id": "collection_ids"}, {"_id": "collection_ids", collection: new}
        )
        return new

    async def get_gas_cog(self, ctx: Context) -> Optional[GlobalActions]:
        cog: GlobalActions = self.bot.get_cog("GlobalActions")  # type: ignore
        if not cog:
            await ctx.reply(
                "This command is unavailable right now, try again later.",
                ephemeral=True,
            )
        return cog if cog else None

    @staticmethod
    def validate_category(
        cog: GlobalActions, category, subcategory
    ) -> List[bool, bool]:
        categories = cog.categories
        check = [False, False]
        if category in categories:
            check[0] = True
        if check[0] and subcategory in categories[category]:
            check[1] = True
        return check

    async def create_draft(
        self,
        ctx: Context,
        user_ids: List[int],
        brief_description: str,
        category: str,
        subcategory: str,
        anonymous: bool,
        server_ids: Optional[List[int]],
    ):
        user_ids = list(set(user_ids))
        if len(brief_description) < 50:
            await ctx.send(
                "Brief description is too short, it must be at least 50 characters."
            )
            return
        if len(brief_description) > 250:
            await ctx.send(
                "Brief description is too long, it must be equal to 250 characters or lower."
            )
            return
        # check how many drafts user already has
        result = await self.bot.db.drafts.find_many({"owner": ctx.author.id})
        if result:
            if len(result) >= 5:
                await ctx.send(
                    "You already have 5 drafted reports, delete one before you make another!"
                )
                return
        cog = await self.get_gas_cog(ctx)
        if not cog:
            return
        cog: GlobalActions
        valid = self.validate_category(cog, category, subcategory)
        if not valid[0]:
            await ctx.reply("invalid category", ephemeral=True)
            return
        elif not valid[1]:
            await ctx.reply("invalid sub category", ephemeral=True)
            return

        # check if user has sent a report and it is on stage 1

        result = await self.bot.db.pollings.find({"owner": ctx.author.id, "stage": 1})
        if result:
            return await ctx.reply(
                f"You have already submitted a report at"
                f" {discord.utils.format_dt(result['created_at'].replace(tzinfo=datetime.timezone.utc))}\n"
                f"You cannot make a new report until the report has been marked as verified"
                f"Note: You do not get notified when a report is marked as verified",
                ephemeral=True,
            )

        # check if any of the users are already reported

        users_reported = []
        for user in user_ids:
            reported = await self.bot.db.pollings.find(
                {"reported_users": {"$all": [user]}}
            )
            if reported:
                users_reported.append(str(user))
        if users_reported:
            return await ctx.reply(
                f"{ctx.humanize_list(users_reported)} have already been reported\n"
                f"If you would like to provide additional information or proof please make a ticket in DDA!",
                ephemeral=True,
            )

        await ctx.send("Creating report draft...", ephemeral=True)
        _id = await self.get_id("draft")

        await self.bot.db.drafts.insert(
            {
                "_id": _id,
                "owner": ctx.author.id,
                "category": category,
                "subcategory": subcategory,
                "attachments": [],
                "reported_users": user_ids,
                "associated_servers": server_ids,
                "brief_description": brief_description,
                "long_description": None,
                "is_anonymous": anonymous,
            }
        )

        await self.send_draft_embed(ctx, _id)

    async def attach_proof(
        self,
        ctx: Context,
        case_id: int,
        attachments: List[Attachment],
        _type: Literal["draft", "poll"],
        message: Optional[discord.Message] = None,
    ):
        ref = self.bot.db.drafts if _type == "draft" else self.bot.db.pollings
        # check how many attachments they already have
        if _type == "draft":
            prev = await ref.find({"_id": case_id, "owner": ctx.author.id})
        else:
            prev = await ref.find(
                {
                    "_id": case_id,
                }
            )
        if not prev:
            await ctx.send(f"Found no instances of {_type} {case_id}", ephemeral=True)
            return

        limit = 15 if _type == "draft" else 25
        if len(prev["attachments"]) + len(attachments) > limit:
            if limit == 15:
                await ctx.send(
                    "Only 15 attachments are allowed, please delete one before you add another!"
                    "\nTo attach more create a ticket in DDA",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    "Maximum attachment [25] for polling pool has been reached!",
                    ephemeral=True,
                )
            return

        def resolve_metadata(attachment: Attachment):
            metadata = attachment.content_type.split("/")
            valid_files = ["png", "jpeg", "jpg"]
            return (
                metadata[0] == "image",
                metadata[1],
                attachment.is_spoiler(),
                metadata[1].lower() in valid_files,
            )

        in_bytes: List[Dict[str, Any]] = prev["attachments"]
        for idx, attachment in enumerate(attachments, start=len(prev["attachments"])):
            metadata = resolve_metadata(attachment)
            if not metadata[0]:
                await ctx.reply(
                    f"Error Attachment Number {idx} is not a image!", ephemeral=True
                )
                return
            elif not metadata[3]:
                await ctx.reply(
                    "Attachment's must be type png, jpeg or jpg!", ephemeral=True
                )
                return
            try:
                resolved = await attachment.read()
                compressed_image = BytesIO()
                image = Image.open(BytesIO(resolved))
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
                image.save(compressed_image, format="JPEG", quality=55, optimize=True)
                compressed_image.seek(0)
                # 'attachment': gzip.compress(resolved), Don't need double compression
                # Only makes a small difference e.g: ~5k bytes
                data = {
                    "attachment": compressed_image.getvalue(),
                    "type": metadata[1],
                    "name": f"attachment_{idx}.{metadata[1]}",
                    "is_spoiler": metadata[2],
                }
                in_bytes.append(data)
            except (discord.NotFound, discord.HTTPException, discord.Forbidden) as e:
                await ctx.reply(
                    f"Attachment Number {idx} raised the error **{e.__class__.__name__}**: `{e}`",
                    ephemeral=True,
                )
                return

        await ref.upsert(
            {"_id": case_id},
            {
                "attachments": in_bytes,
            },
        )
        await ctx.reply(f"Added attachments to case: {case_id}", ephemeral=True)
        if message:
            prev["attachments"] = in_bytes
            view = None
            if prev["stage"] == 1:
                view = VerifyReportView(
                    self.bot,
                    prev,
                )
            elif prev["stage"] == 2:
                view = PollingView(self.bot, prev)
            if view:
                await message.edit(view=view)

    @staticmethod
    def format_attachments(attachments: List[Dict[str, Any]]) -> List[discord.File]:
        files: List[discord.File] = []
        for attachment in attachments:
            # BytesIO(gzip.decompress(attachment['attachment'])),
            files.append(
                discord.File(
                    BytesIO(attachment["attachment"]),
                    filename=attachment["name"],
                    spoiler=attachment["is_spoiler"],
                )
            )
        return files

    async def send_draft_embed(self, ctx: Context, case_id: int):
        draft = await self.bot.db.drafts.find({"_id": case_id, "owner": ctx.author.id})
        if not draft:
            await ctx.send(f"No draft report found for {case_id}!")
            return

        description = (
            f"**Reported Users**: {' '.join(map(str, draft['reported_users']))}\n"
            f"**Category**: {draft['category']}\n**Subcategory**: {draft['subcategory']}\n"
            f"**Anonymous**: {draft['is_anonymous']}\n"
            f"**Servers Involved**: {' '.join(map(str, (draft['associated_servers']) or ['None']))}"
        )
        embed = discord.Embed(
            title=f"Report Draft {case_id}",
            description=description,
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Brief Description", value=draft["brief_description"])
        view = DraftView(ctx, draft)
        await self.bot.reminder.create_timer(
            discord.utils.utcnow() + datetime.timedelta(days=7),
            "draft_expire",
            data=draft,
        )
        message = await ctx.send(
            content="⚠️ Draft's are deleted after 7 days.",
            embed=embed,
            view=view,
            ephemeral=True,
        )
        view.message = message
