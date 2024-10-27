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

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import floor
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord
from discord import Interaction
from discord.ext import commands
from discord.ui import Modal, View, button

from cogs.global_actions import Actions, MaxDuration, ScopeTypes
from utils.time import TimeTransformer, human_timedelta

from .converters import GuildsConverter, UsersConverter

if TYPE_CHECKING:
    from bot import PhantomGuard
    from cogs.global_actions import GlobalActions
    from utils.context import Context

    from .reports import Reports


class AttachmentPaginator(View):
    def __init__(
        self,
        ctx: Context,
        data: Dict,
        attachments: List[discord.File],
        viewing_only: bool = False,
        timeout: int = 300,
    ):
        super().__init__(timeout=timeout)
        self.ctx: Context = ctx
        self.data: Dict = data
        self.case_id: int = data["_id"]
        self.attachments: List[discord.File] = attachments
        self.deleted: Dict[int, bool] = {k: False for k in range(len(attachments))}
        self.index: int = 0
        self.previous_page.disabled = True
        if len(attachments) == 1:
            self.next_page.disabled = True
        self.current_page.label = f"{self.index + 1}"
        self.original_message: Optional[discord.Message] = None
        self.viewing_only: bool = viewing_only
        if self.viewing_only:
            self.clear_items()
            self.fill_items()

    def fill_items(self):
        self.save_and_quit.label = "Quit"
        self.save_and_quit.style = discord.ButtonStyle.red
        items = [
            self.previous_page,
            self.current_page,
            self.next_page,
            self.save_and_quit,
        ]
        for item in items:
            self.add_item(item)

    async def on_save(self, interaction: Interaction) -> None:
        if self.viewing_only:
            return
        attachments: Dict[int, bool] = filter(
            lambda x: x[1] is False, self.deleted.items()
        )
        attachments: List[discord.File] = [
            self.attachments[idx[0]] for idx in attachments
        ]
        deleted_amount = len(self.attachments) - len(attachments)
        if len(attachments) != len(self.attachments):
            final_attachments: List[Dict[str, Any]] = []
            for idx, attachment in enumerate(attachments):
                ending = attachment.filename.split(".")[-1]
                data = {
                    "attachment": attachment.fp.read(),
                    "type": ending,
                    "name": f"attachment_{idx}.{ending}",
                    "is_spoiler": attachment.spoiler,
                }
                final_attachments.append(data)

            await self.ctx.bot.db.drafts.update(
                {
                    "_id": self.case_id,
                },
                {
                    "attachments": final_attachments,
                },
            )
            self.data["attachments"] = final_attachments
        await interaction.followup.send(
            f"You have deleted {deleted_amount:,} draft attachment."
            f"\nYou have {len(attachments):,} Attachments for Draft ID: `{self.case_id}`",
            ephemeral=True,
        )

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.viewing_only:
            return True
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    async def on_timeout(self):
        if self.original_message:
            try:
                await self.original_message.edit(view=None)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                pass

    async def update_paginator(self, interaction: discord.Interaction, offset: int):
        self.index += offset

        if self.previous_page.disabled:
            self.previous_page.disabled = False
        if self.next_page.disabled:
            self.next_page.disabled = False

        if self.index == len(self.attachments) - 1:
            self.next_page.disabled = True

        if self.index == 0:
            self.previous_page.disabled = True

        new_attachment = self.attachments[self.index]
        try:
            embed = self.original_message.embeds[0]
        except KeyError:
            embed = discord.Embed(
                title=f"Attachment {self.index + 1}/{len(self.attachments)}",
                colour=discord.Color.blurple(),
            )

        embed.set_image(url=f"attachment://{new_attachment.filename}")
        self.current_page.label = f"{self.index + 1}"
        if self.deleted[self.index]:
            self.manage_attachment.style = discord.ButtonStyle.green
            self.manage_attachment.label = "Restore Attachment"
        else:
            self.manage_attachment.style = discord.ButtonStyle.red
            self.manage_attachment.label = "Delete Attachment"

        try:
            if interaction.response.is_done():
                if self.original_message:
                    await self.original_message.edit(
                        embed=embed, view=self, file=deepcopy(new_attachment)
                    )
            else:
                await interaction.response.edit_message(
                    embed=embed, view=self, attachments=[deepcopy(new_attachment)]
                )

        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            pass

    @button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous_page(self, inter: discord.Interaction, btn: discord.Button):
        await self.update_paginator(inter, -1)

    @button(style=discord.ButtonStyle.grey, disabled=True)
    async def current_page(self, inter: discord.Interaction, btn: discord.Button):
        """displays the current page!"""
        pass

    @button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_page(self, inter: discord.Interaction, btn: discord.Button):
        await self.update_paginator(inter, 1)

    @button(label="Delete Attachment", style=discord.ButtonStyle.red)
    async def manage_attachment(self, inter: discord.Interaction, btn: discord.Button):
        if btn.label == "Delete Attachment":
            self.deleted[self.index] = True
            btn.style = discord.ButtonStyle.green
            btn.label = "Restore Attachment"
        else:
            self.deleted[self.index] = False
            btn.style = discord.ButtonStyle.red
            btn.label = "Delete Attachment"
        await inter.response.edit_message(view=self)

    @button(label="Save & Quit", style=discord.ButtonStyle.grey)
    async def save_and_quit(self, inter: discord.Interaction, btn: discord.Button):
        await inter.response.defer(ephemeral=True)
        await self.on_save(inter)
        await inter.delete_original_response()
        self.stop()


class DescriptionModal(Modal, title="Description"):
    def __init__(
        self,
        ctx: Context,
        data: Dict,
    ):
        super().__init__()
        self.ctx: Context = ctx
        self.data: Dict = data
        self.brief_description = discord.ui.TextInput(
            label="brief_description",
            style=discord.TextStyle.long,
            placeholder="250 character short description",
            default=self.data["brief_description"],
            required=True,
            max_length=250,
            min_length=50,
        )
        self.long_description = discord.ui.TextInput(
            label="Long description",
            style=discord.TextStyle.long,
            placeholder="4K character long description",
            default=self.data["long_description"],
            required=True,
            min_length=100,
            max_length=4_000,
        )

        self.add_item(self.brief_description)
        self.add_item(self.long_description)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        changes: List[bool] = [False, False]
        if self.data["brief_description"] != self.brief_description.value:
            changes[0] = True
        if self.data["long_description"] != self.long_description.value:
            changes[1] = True
        if any(changes):
            self.data["brief_description"] = self.brief_description.value
            self.data["long_description"] = self.long_description.value
            await self.ctx.bot.db.drafts.update(
                {"_id": self.data["_id"]},
                {
                    "_id": self.data["_id"],
                    "long_description": self.long_description.value,
                    "brief_description": self.brief_description.value,
                },
            )

            await interaction.followup.send(
                f'Updated Draft `{self.data['_id']}`\'s Description', ephemeral=True
            )
        else:
            await interaction.followup.send(
                f'No changes were made to Draft `{self.data["id"]}`\'s Descriptions',
                ephemeral=True,
            )


class DraftFields(Modal, title="Edit Fields"):
    def __init__(
        self,
        ctx: Context,
        data: Dict,
        message: Optional[discord.Message],
        valid_categories: Dict[str, List[str]],
    ):
        super().__init__()
        self.ctx: Context = ctx
        self.data: Dict = data
        self.message: Optional[discord.Message] = message
        self.valid_categories: Dict[str, List[str]] = valid_categories
        self.users = discord.ui.TextInput(
            label="Users",
            style=discord.TextStyle.short,
            placeholder="ID1 ID2 ID3 ...",
            default=" ".join(map(str, data["reported_users"])),
            required=True,
            min_length=15,
            max_length=200,
        )
        self.servers = discord.ui.TextInput(
            label="Servers",
            style=discord.TextStyle.short,
            placeholder="ID1 ID2 ID3 ...",
            default=" ".join(map(str, (data["associated_servers"] or ["None"]))),
            required=False,
            min_length=0,
            max_length=200,
        )
        self.category = discord.ui.TextInput(
            label="Category",
            style=discord.TextStyle.short,
            placeholder="discord_tos",
            default=data["category"],
            required=True,
            min_length=4,
            max_length=75,
        )
        self.subcategory = discord.ui.TextInput(
            label="Subcategory",
            style=discord.TextStyle.short,
            placeholder="nsfw",
            default=data["subcategory"],
            required=True,
            min_length=4,
            max_length=75,
        )
        self.anonymous = discord.ui.TextInput(
            label="Anonymous",
            style=discord.TextStyle.short,
            placeholder="true/false",
            default=str(data["is_anonymous"]),
            required=True,
            min_length=4,
            max_length=5,
        )
        self.add_item(self.users)
        self.add_item(self.servers)
        self.add_item(self.category)
        self.add_item(self.subcategory)
        self.add_item(self.anonymous)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        changes = [None, None, None, None, None]
        # in order of: users, servers, category, subcategory, anonymous
        # first we validate and respond if anything is invalid.
        if len(self.data["reported_users"]) != len(self.users.value.split(" ")):
            try:
                users = await UsersConverter().convert(self.ctx, self.users.value)
            except commands.BadArgument:
                users = None
            if not users:
                await interaction.followup.send("No Users found.", ephemeral=True)
                return
            changes[0] = [u.id for u in users]

        if len(self.data["associated_servers"] or ["none"]) != len(
            self.servers.value.split(" ")
        ):
            try:
                servers = await GuildsConverter().convert(self.ctx, self.servers.value)
            except commands.BadArgument:
                servers = None
            if not servers:
                await interaction.followup.send("No Servers found.", ephemeral=True)
                return
            changes[1] = [g.id for g in servers]

        if self.data["category"] != self.category.value:
            if self.category.value.lower() not in self.valid_categories:
                await interaction.followup.send("Invalid Category!", ephemeral=True)
                return
            changes[2] = self.category.value.lower()
            if (
                self.subcategory.value.lower()
                not in self.valid_categories[self.category.value.lower()]
            ):
                await interaction.followup.send("Invalid Subcategory!", ephemeral=True)
                return
            changes[3] = self.subcategory.value.lower()

        def format_anony(value) -> Optional[bool]:
            valid: Dict[bool, List[str]] = {
                True: ["true", "1", "yes", "y"],
                False: ["false", "0", "no", "n"],
            }
            for key, pair in valid.items():
                if value.lower() in pair:
                    return key

        if str(self.data["is_anonymous"]).lower() != self.anonymous.value.lower():
            if self.anonymous.value:
                anonymous = format_anony(self.anonymous.value.lower())
                if anonymous is None:
                    await interaction.followup.send(
                        "Invalid value, must be (true, 1, yes, y) or (false, 1, yes, y)!",
                        ephemeral=True,
                    )
                    return
                changes[4] = anonymous
        if any(changes) or changes[4] is not None:
            update_dict = {}
            names: List[str] = [
                "reported_users",
                "associated_servers",
                "category",
                "subcategory",
                "is_anonymous",
            ]
            for idx, name in enumerate(names):
                if changes[idx] is not None:
                    update_dict[name] = changes[idx]
                    self.data[name] = changes[idx]

            await self.ctx.bot.db.drafts.update(
                {
                    "_id": self.data["_id"],
                },
                update_dict,
            )
            self.data.update(update_dict)
            description = (
                f"**Reported Users**: {' '.join(map(str, self.data['reported_users']))}\n"
                f"**Category**: {self.data['category']}\nSub category: {self.data['subcategory']}\n"
                f"**Anonymous**: {self.data['is_anonymous']}\n"
                f"**Servers Involved**: {' '.join(map(str, (self.data['associated_servers'] or ["None"]))).strip()}"
            )
            embed = discord.Embed(
                title=f"Report Draft {self.data['_id']}",
                description=description,
                colour=discord.Colour.blurple(),
            )
            embed.add_field(
                name="Brief Description", value=self.data["brief_description"]
            )
            if self.message:
                try:
                    await self.message.edit(embed=embed)
                except Exception:
                    self.message = None
                    pass
            await interaction.followup.send(
                f"Updated {len([c for c in changes if c is not None])} field(s)!",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f'No changes were made to draft `{self.data["_id"]}`\'s Fields',
            ephemeral=True,
        )


class DraftView(View):
    def __init__(self, ctx: Context, data: Dict, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.ctx: Context = ctx
        self.data = data
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    @button(label="Description", style=discord.ButtonStyle.blurple)
    async def description(self, inter: discord.Interaction, btn: discord.Button):
        # send modal with the brief (250 chr) + Long description (4k chr)
        await inter.response.send_modal(DescriptionModal(self.ctx, self.data))

    @button(label="Attachments", style=discord.ButtonStyle.grey)
    async def attachments(self, inter: discord.Interaction, btn: discord.Button):
        if not self.data["attachments"]:
            return await inter.response.send_message(
                "You don't have any attachments added!", ephemeral=True
            )
        if not inter.channel.permissions_for(inter.guild.me).embed_links:
            await inter.response.send_message(
                "Bot does not have embed links permission in this channel.",
                ephemeral=True,
            )
            return
        cog = self.ctx.bot.get_cog("Reports")
        if not cog:
            return await inter.response.send_message(
                "This feature is unavailable right now!", ephemeral=True
            )
        cog: Reports

        await inter.response.defer(ephemeral=True)

        paginator = AttachmentPaginator(
            self.ctx,
            self.data,
            attachments=cog.reports.format_attachments(self.data["attachments"]),
        )
        embed = discord.Embed(
            title=f"Attachment's For draft `{self.data['_id']}`. [1/{len(paginator.attachments)}]",
            colour=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{paginator.attachments[0].filename}")
        message = await inter.followup.send(
            embed=embed,
            view=paginator,
            ephemeral=True,
            file=deepcopy(paginator.attachments[0]),
        )
        paginator.original_message = message

    @button(label="Edit Fields", style=discord.ButtonStyle.blurple)
    async def edit_fields(self, inter: discord.Interaction, btn: discord.Button):
        cog = self.ctx.bot.get_cog("GlobalActions")
        if not cog:
            await inter.response.send_message(
                "This feature is unavailable at the moment.", ephemeral=True
            )
            return
        cog: GlobalActions
        await inter.response.send_modal(
            DraftFields(self.ctx, self.data, self.message, cog.categories)
        )

    @button(label="Submit Draft", style=discord.ButtonStyle.red)
    async def submit_draft(self, inter: discord.Interaction, btn: discord.Button):
        if not self.data["attachments"]:
            return await inter.response.send_message(
                "There must be at least one proof attachment!", ephemeral=True
            )

        if not self.data["long_description"]:
            return await inter.response.send_message(
                "Long Description is required Field and is missing!", ephemeral=True
            )

        # send to polling and add to reports db and delete from drafts
        cog = self.ctx.bot.get_cog("Reports")
        if not cog:
            await inter.response.send_message(
                "This feature is currently unavailable!", ephemeral=True
            )
            return
        cog: Reports
        result = await cog.polling.create_draft_polling(self.data)
        if result is True:
            return await inter.response.send_message("Created Report!", ephemeral=True)
        elif result is False:
            return await inter.response.send_message(
                "Error: Draft no longer exists!", ephemeral=True
            )
        else:
            return await inter.response.send_message(
                "This feature is currently unavailable", ephemeral=True
            )


class SanctionsPaginator(View):
    def __init__(self, bot: PhantomGuard, sanctions: Dict, author_id: int):
        super().__init__()
        self.bot: PhantomGuard = bot
        self.sanctions: List[discord.Embed] = []
        self.author_id: int = author_id
        self.total = len(sanctions)
        for idx, sanction in enumerate(sanctions, start=1):
            expires: Optional[float] = sanction["expires"]
            if expires:
                expires: datetime = discord.utils.utcnow() + timedelta(seconds=expires)
            human_scope = str(ScopeTypes.from_str(sanction["scope"]))
            guild_stats = len(sanction["guild_ids"]) if sanction["guild_ids"] else None
            embed = discord.Embed(
                title=f"Sanction {idx}/{self.total}",
                description=(
                    f"**Users**: {' '.join(map(str, sanction['users']))}\n"
                    f"**Sanction**: {str(Actions.from_str(sanction['action']))}\n"
                    f"**Duration**: {human_timedelta(expires) if expires else 'None'}\n"
                    f"**Guilds**: {human_scope} {f'[ {guild_stats:,} ]'if guild_stats else ''}"
                ),
            )
            embed.add_field(name="reason", value=sanction["reason"])
            self.sanctions.append(embed)
        self.index: int = 0
        self.previous_page.disabled = True
        if len(sanctions) == 1:
            self.next_page.disabled = True
        self.current_page.label = f"{self.index + 1}"
        self.original_message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    async def on_timeout(self):
        if self.original_message:
            try:
                await self.original_message.edit(view=None)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                pass

    async def update_paginator(self, interaction: discord.Interaction, offset: int):
        self.index += offset

        if self.previous_page.disabled:
            self.previous_page.disabled = False
        if self.next_page.disabled:
            self.next_page.disabled = False

        if self.index == len(self.sanctions) - 1:
            self.next_page.disabled = True

        if self.index == 0:
            self.previous_page.disabled = True

        embed = self.sanctions[self.index]
        self.current_page.label = f"{self.index + 1}"
        try:
            if interaction.response.is_done():
                if self.original_message:
                    await self.original_message.edit(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            pass

    @button(label="previous", style=discord.ButtonStyle.blurple, row=0)
    async def previous_page(
        self, interaction: discord.Interaction, btn: discord.Button
    ):
        await self.update_paginator(interaction, -1)

    @button(style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def current_page(self, interaction: discord.Interaction, btn: discord.Button):
        pass

    @button(label="next", style=discord.ButtonStyle.blurple, row=0)
    async def next_page(self, interaction: discord.Interaction, btn: discord.Button):
        await self.update_paginator(interaction, 1)

    @button(label="quit", style=discord.ButtonStyle.red, row=0)
    async def quit(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.defer(ephemeral=True)
        if self.original_message:
            await self.original_message.edit(view=None)
        self.stop()


class OptionsPaginator(View):
    def __init__(
        self,
        bot: PhantomGuard,
        data: Dict,
        with_voting: bool = True,
        view: Optional[PollingView] = None,
    ):
        super().__init__()
        self.bot: PhantomGuard = bot
        self.data: Dict = data
        self.view: Optional[PollingView] = view
        self.original_view = view
        self.options: List[discord.Embed] = []
        self.total = len(data["options"])

        for idx, option in enumerate(data["options"], start=1):
            owner = bot.get_user(option["owner"])
            if owner:
                owner = f"{owner.name} | `{owner.id}`"
            else:
                owner = f"`{option['owner']}`"
            embed = discord.Embed(
                title=f"Option {idx}/{self.total}",
                description=(
                    (
                        f"**Author**: {owner}\n"
                        f"**Addressing Mode**: {option['addressing_type']}\n"
                        f"**Attachments**: {' '.join([str(idx) for idx, _ in enumerate(option['attachments'], start=1)])}\n"
                        + (
                            f"**Votes For**: `{floor(option['polling']['points']['for'])}`\n"
                            f"**Votes Against**: `{floor(option['polling']['points']['against'])}`\n"
                            f"**For**: {', '.join(map(str, option['polling']['users']['for']))}\n"
                            f"**Against**: {', '.join(map(str, option['polling']['users']['against']))}"
                        )
                        if with_voting
                        else ""
                    ).strip()
                ),
            )
            self.options.append(embed)
        self.index: int = 0
        self.previous_page.disabled = True
        if len(data["options"]) == 1:
            self.next_page.disabled = True
        self.current_page.label = f"{self.index + 1}"
        self.original_message: Optional[discord.Message] = None
        self.points: Dict[str, float] = {"admin": 2.0, "mod": 1.0}
        self.threshold: int = 5
        self.original_message = None
        self.clear_items()
        self.fill_items(with_voting)

    def fill_items(self, with_voting: bool):
        if with_voting:
            to_display = [
                self.previous_page,
                self.current_page,
                self.next_page,
                self.quit,
                self.vote_for,
                self.view_sanctions,
                self.vote_against,
            ]
        else:
            to_display = [self.view_sanctions, self.quit]

        for item in to_display:
            self.add_item(item)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if (
            interaction.user.id in self.bot.mods
            or interaction.user.id in self.bot.admins
        ):
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    async def on_timeout(self):
        if self.original_message:
            try:
                await self.original_message.edit(view=None)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                pass

    async def update_paginator(self, interaction: discord.Interaction, offset: int):
        self.index += offset

        if self.previous_page.disabled:
            self.previous_page.disabled = False
        if self.next_page.disabled:
            self.next_page.disabled = False

        if self.index == len(self.options) - 1:
            self.next_page.disabled = True

        if self.index == 0:
            self.previous_page.disabled = True

        embed = self.options[self.index]
        self.current_page.label = f"{self.index + 1}"
        try:
            if interaction.response.is_done():
                if self.original_message:
                    await self.original_message.edit(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            pass

    @button(label="previous", style=discord.ButtonStyle.blurple, row=0)
    async def previous_page(
        self, interaction: discord.Interaction, btn: discord.Button
    ):
        await self.update_paginator(interaction, -1)

    @button(style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def current_page(self, interaction: discord.Interaction, btn: discord.Button):
        pass

    @button(label="next", style=discord.ButtonStyle.blurple, row=0)
    async def next_page(self, interaction: discord.Interaction, btn: discord.Button):
        await self.update_paginator(interaction, 1)

    @button(label="quit", style=discord.ButtonStyle.red, row=0)
    async def quit(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.defer(ephemeral=True)
        await self.on_timeout()
        self.stop()

    @button(label="vote for", style=discord.ButtonStyle.green, row=1)
    async def vote_for(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id in self.bot.admins:
            points = self.points["admin"]
        else:
            points = self.points["mod"]
        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await interaction.followup.send("This poll has expired.", ephemeral=True)
            return
        polling = self.data["options"][self.index]["polling"]
        if interaction.user.id in polling["users"]["against"]:
            polling["points"]["against"] -= points
            (polling["users"]["against"].remove(interaction.user.id),)

        if interaction.user.id not in polling["users"]["for"]:
            polling["points"]["for"] += points
            polling["users"]["for"].append(interaction.user.id)
        else:
            await interaction.followup.send(
                "You have already voted for this option!", ephemeral=True
            )
            return
        update_dict = {
            "options": self.data["options"],
        }
        im_flag = (
            self.data["options"][self.index]["addressing_type"] == "immediate"
            and polling["points"]["for"] >= 5
        )
        if im_flag:
            update_dict["type"] = "ended"

        await self.bot.db.pollings.update({"_id": self.data["_id"]}, update_dict)
        embed = self.options[self.index]
        option = self.data["options"][self.index]
        description = (
            f"**Owner**: {option['owner']}\n"
            f"**Attachments**: {' '.join([str(idx) for idx, _ in enumerate(option['attachments'], start=1)])}\n"
            f"**Votes For**: `{floor(polling['points']['for'])}`\n"
            f"**Votes Against**: `{floor(polling['points']['against'])}`\n"
            f"**For**: {', '.join(map(str, option['polling']['users']['for']))}\n"
            f"**Against**: {', '.join(map(str, option['polling']['users']['against']))}"
        )
        embed.description = description
        await interaction.edit_original_response(embed=embed)
        await interaction.followup.send(
            "You have voted for this option!", ephemeral=True
        )
        if im_flag:

            class TimerProxy:
                def __init__(self, data):
                    self.kwargs: Dict = {"data": data}

            self.bot.dispatch("poll_timer_complete", TimerProxy(self.data))
            self.stop()
            self.view.stop()

    @button(label="view sanctions", style=discord.ButtonStyle.grey, row=1)
    async def view_sanctions(
        self, interaction: discord.Interaction, btn: discord.Button
    ):
        if not self.data["options"][self.index]["sanctions"]:
            return await interaction.response.send_message(
                "No sanctions found!", ephemeral=True
            )
        pointer = self.data["options"][self.index]
        view = SanctionsPaginator(self.bot, pointer["sanctions"], interaction.user.id)
        await interaction.response.send_message(
            embed=view.sanctions[0], view=view, ephemeral=True
        )
        view.original_message = await interaction.original_response()

    @button(label="vote against", style=discord.ButtonStyle.red, row=1)
    async def vote_against(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id in self.bot.admins:
            points = self.points["admin"]
        else:
            points = self.points["mod"]

        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await interaction.followup.send("This poll has expired.", ephemeral=True)
            return
        polling = self.data["options"][self.index]["polling"]
        if interaction.user.id in polling["users"]["for"]:
            polling["points"]["for"] -= points
            polling["users"]["for"].remove(interaction.user.id)
        if interaction.user.id not in polling["users"]["against"]:
            polling["points"]["against"] += points
            polling["users"]["against"].append(interaction.user.id)
        else:
            await interaction.followup.send(
                "You have already voted against this option!", ephemeral=True
            )
            return

        update_dict = {
            "options": self.data["options"],
        }
        await self.bot.db.pollings.update({"_id": self.data["_id"]}, update_dict)
        embed = self.options[self.index]
        option = self.data["options"][self.index]
        description = (
            f"**Author**: {option['owner']}\n"
            f"**Attachments**: {' '.join([str(idx) for idx, _ in enumerate(option['attachments'], start=1)])}\n"
            f"**Votes For**: `{floor(polling['points']['for'])}`\n"
            f"**Votes Against**: `{floor(polling['points']['against'])}`\n"
            f"**For**: {', '.join(map(str, option['polling']['users']['for']))}\n"
            f"**Against**: {', '.join(map(str, option['polling']['users']['against']))}"
        )
        embed.description = description
        await interaction.edit_original_response(embed=embed)
        await interaction.followup.send(
            "You have voted for this option!", ephemeral=True
        )


class AddSanctionModal(Modal, title="Add Sanction"):
    def __init__(self, view: "CreateOptionsView"):
        super().__init__()
        self.view: "CreateOptionsView" = view
        self.users = discord.ui.TextInput(
            label="User ID(S)",
            style=discord.TextStyle.short,
            placeholder="User ID(S)",
            required=True,
            min_length=15,
            max_length=1000,
        )
        self.action = discord.ui.TextInput(
            label="Action Type",
            style=discord.TextStyle.short,
            placeholder="Action Types: Ban, Kick, Quarantine, Mute, None",
            required=True,
            min_length=3,
            max_length=10,
        )
        self.duration = discord.ui.TextInput(
            label="Duration",
            style=discord.TextStyle.short,
            placeholder="365d, 786h or 30m etc",
            required=False,
            min_length=2,
            max_length=15,
        )
        self.guild_ids = discord.ui.TextInput(
            label="Scope",
            style=discord.TextStyle.short,
            placeholder="global, mutual or type guild ids separated by a space. e.g: s1 s2 ...",
            required=True,
            min_length=6,
            max_length=1000,
        )
        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.long,
            placeholder="The Reason for why these specific users get this action!",
            required=True,
            min_length=100,
            max_length=2000,
        )
        for item in [
            self.users,
            self.action,
            self.duration,
            self.guild_ids,
            self.reason,
        ]:
            self.add_item(item)

    async def on_submit(self, interaction: Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            users = await UsersConverter().convert(
                interaction, self.users.value.lower()
            )
        except commands.BadArgument:
            users = None
        if not users:
            await interaction.followup.send("ERROR: No users resolved!", ephemeral=True)
            return
        users = [u.id for u in users]
        if self.guild_ids.value.lower() not in ["global", "mutual"]:
            try:
                guilds = await GuildsConverter().convert(
                    interaction, self.guild_ids.value.lower()
                )
            except commands.BadArgument:
                guilds = None
            if not guilds:
                await interaction.followup.send(
                    "ERROR: No guilds resolved!", ephemeral=True
                )
                return
            guilds = [g.id for g in guilds]
        else:
            guilds = self.guild_ids.value.lower()
        actions: List[str] = [
            str(action)
            for action in [
                Actions.NONE,
                Actions.WARN,
                Actions.MUTE,
                Actions.QUARANTINE,
                Actions.KICK,
                Actions.BAN,
            ]
        ]
        if self.action.value.lower() not in actions:
            await interaction.followup.send("ERROR: Invalid action!", ephemeral=True)
            return

        duration = None
        if self.duration.value:
            try:
                duration = await TimeTransformer().transform(
                    interaction, self.duration.value
                )
                now = discord.utils.utcnow()
                duration = duration.timestamp() - now.timestamp()
                max_duration_enum = MaxDuration.from_str(self.action.value.lower())
                if max_duration_enum.value == 0:
                    return await interaction.followup.send(
                        f"ERROR: The action {self.action.value.lower()} cannot have a duration!",
                        ephemeral=True,
                    )
                max_duration = now + timedelta(days=max_duration_enum.value)
                max_duration = max_duration.timestamp() - now.timestamp()
                if duration > max_duration:
                    return await interaction.followup.send(
                        f"ERROR: The action {self.action.value.lower()} must have a duration smaller than or equal to"
                        f" {max_duration_enum.value} days!",
                        ephemeral=True,
                    )
            except Exception:
                await interaction.followup.send(
                    "ERROR: Invalid duration!", ephemeral=True
                )
                return

        if duration is None and self.action.value.lower() in ["mute"]:
            return await interaction.followup.send(
                f"Duration is a required argument and is missing for action {self.action.value.lower()}",
                ephemeral=True,
            )

        self.view.add_sanction(
            users,
            self.action.value.lower(),
            duration,
            self.reason.value,
            guilds if not isinstance(guilds, list) else "targeted",
            guilds if isinstance(guilds, list) else None,
        )
        await interaction.followup.send("Added Sanction!", ephemeral=True)


class SetFieldsModal(Modal, title="Edit Fields"):
    def __init__(self, view: "CreateOptionsView"):
        super().__init__()
        self.view = view
        self.addressing_type: discord.ui.TextInput = discord.ui.TextInput(
            label="Addressing Type",
            style=discord.TextStyle.short,
            placeholder="non-immediate / immediate",
            default=view.option["addressing_type"],
            required=True,
            min_length=9,
            max_length=13,
        )
        self.category: discord.ui.TextInput = discord.ui.TextInput(
            label="Category",
            style=discord.TextStyle.short,
            placeholder="Category1",
            default=view.data["category"],
            required=True,
            min_length=3,
            max_length=15,
        )
        self.subcategory: discord.ui.TextInput = discord.ui.TextInput(
            label="Subcategory",
            style=discord.TextStyle.short,
            placeholder="Subcategory1",
            default=view.data["subcategory"],
            required=True,
            min_length=3,
            max_length=15,
        )
        self.attachments: discord.ui.TextInput = discord.ui.TextInput(
            label="Attachments",
            style=discord.TextStyle.short,
            placeholder="1 4 5 (use a space in between index's)",
            default=" ".join(
                [str(idx + 1) for idx, _ in enumerate(self.view.option["attachments"])]
            )
            if self.view.option["attachments"]
            else None,
            required=True,
            min_length=1,
            max_length=150,
        )
        for item in [
            self.addressing_type,
            self.category,
            self.subcategory,
            self.attachments,
        ]:
            self.add_item(item)

    async def on_submit(self, interaction: Interaction) -> None:
        try:
            categories = getattr(self.view, "categories")
        except AttributeError:
            await interaction.response.send_message(
                "This feature is unavailable right now.", ephemeral=True
            )
            return

        if self.category.value.lower() not in categories:
            await interaction.response.send_message("Invalid Category", ephemeral=True)
            return
        if (
            self.subcategory.value.lower()
            not in categories[self.category.value.lower()]
        ):
            await interaction.response.send_message(
                "Invalid Subcategory", ephemeral=True
            )
            return
        if self.addressing_type.value.lower() not in ["non-immediate", "immediate"]:
            await interaction.response.send_message(
                "Addressing Type must be either `non-immediate` or `immediate`",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        attachments = []
        total_attachments_in_pool = len(self.view.data["attachments"])
        for value in self.attachments.value.lower().strip().split(" "):
            if value == "":
                continue
            if not value.isdigit():
                return await interaction.followup.send(
                    f"{value} is not a digit!", ephemeral=True
                )
            resolved = int(value)
            if resolved <= 0:
                return await interaction.followup.send(
                    f"{resolved} is not a positive number!", ephemeral=True
                )
            if resolved > total_attachments_in_pool:
                return await interaction.followup.send(
                    f"{resolved} is not a valid attachment, the highest value is {total_attachments_in_pool}.",
                    ephemeral=True,
                )
            attachments.append(self.view.data["attachments"][resolved - 1])
        if not len(attachments):
            return await interaction.followup.send(
                "No valid attachments found!", ephemeral=True
            )

        self.view.option["addressing_type"] = self.addressing_type.value.lower()
        self.view.option["category"] = self.category.value.lower()
        self.view.option["subcategory"] = self.subcategory.value.lower()
        self.view.option["attachments"] = attachments
        await interaction.followup.send("Set Fields Successfully!", ephemeral=True)


class CreateOptionsView(View):
    def __init__(self, owner: int, bot: PhantomGuard, data: Dict):
        super().__init__()
        self.bot: PhantomGuard = bot
        cog = self.bot.get_cog("GlobalActions")
        if cog:
            cog: GlobalActions
            self.categories = cog.categories
        self.data: Dict = data
        self.owner: int = owner
        self.users_sanctioned: Dict[str, List] = {
            "reported_users": [],
            "unreported_users": [],
        }
        self.option_idx: Optional[int] = None
        self.option: Dict[str, Any] = {
            "owner": owner,
            "addressing_type": None,
            "category": None,
            "sub_category": None,
            "attachments": [
                # {attachment...}
            ],
            "sanctions": [
                # {
                # "users": []
                # "action": str
                # "expires": None / stamp
                # "reason": ...
                # "scope": str
                # guild_ids: [...] (if targeted ones entered) / None
                # }
            ],
            "polling": {
                "points": {"for": 0, "against": 0},
                "users": {"for": [], "against": []},
            },
        }
        for idx, option in enumerate(self.data["options"]):
            if option["owner"] == self.owner:
                self.option = option
                self.option_idx = idx
                self.decider.label = "Delete"
                self.clear_items()
                self.fill_items()

    def fill_items(self):
        self.decider.row = 0
        self.view.row = 0
        items = [self.view, self.decider, self.quit]
        for item in items:
            self.add_item(item)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    def add_sanction(
        self,
        users: List[int],
        action: str,
        expires: Optional[float],
        reason: str,
        scope: str,
        guild_ids: Optional[List[int]],
    ):
        self.option["sanctions"].append(
            {
                "users": users,
                "action": action,
                "expires": expires,
                "reason": reason,
                "scope": scope,
                "guild_ids": guild_ids,
            }
        )
        users_reported = self.data["reported_users"]
        for user in users:
            if (
                user in users_reported
                and user not in self.users_sanctioned["reported_users"]
            ):
                self.users_sanctioned["reported_users"].append(user)
            elif user not in self.users_sanctioned["unreported_users"]:
                self.users_sanctioned["unreported_users"].append(user)

    @button(label="Add Sanctions", style=discord.ButtonStyle.red, row=0)
    async def add_sanctions(
        self, interaction: discord.Interaction, btn: discord.Button
    ):
        await interaction.response.send_modal(AddSanctionModal(self))

    @button(label="Set Fields", style=discord.ButtonStyle.blurple, row=0)
    async def set_fields(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.send_modal(SetFieldsModal(self))

    @button(label="Quit", style=discord.ButtonStyle.red, row=0)
    async def quit(self, interaction: discord.Interaction, btn: discord.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
        self.stop()

    @button(label="View", style=discord.ButtonStyle.gray, row=1)
    async def view(self, interaction: discord.Interaction, btn: discord.Button):
        embed = discord.Embed(
            title="Your option detail",
            description=f"**Author**: {self.option['owner']}",
        )
        view = OptionsPaginator(self.bot, {"options": [self.option]}, with_voting=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await interaction.original_response()

    @button(label="Create", style=discord.ButtonStyle.green, row=1)
    async def decider(self, interaction: discord.Interaction, btn: discord.Button):
        """if the button should "create" or "Delete" depends upon its label"""
        if btn.label == "Delete":
            if self.option_idx is not None:
                del self.data["options"][self.option_idx]
                await self.bot.db.pollings.update(
                    {"_id": self.data["_id"]}, {"options": self.data["options"]}
                )
                self.option_idx = None
                await self.on_timeout()
                return await interaction.response.send_message(
                    "Deleted Option", ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "Option Not Found", ephemeral=True
                )

        elif btn.label == "Create":
            await interaction.response.defer(ephemeral=True)
            if not self.option["addressing_type"]:
                return await interaction.followup.send(
                    "Addressing Type not set!", ephemeral=True
                )
            if not self.option["category"]:
                return await interaction.followup.send(
                    "Category not set!", ephemeral=True
                )
            if not self.option["subcategory"]:
                return await interaction.followup.send(
                    "Sub Category not set!", ephemeral=True
                )
            if not self.option["attachments"]:
                return await interaction.followup.send(
                    "At least one attachment is required", ephemeral=True
                )
            if not self.option["sanctions"]:
                return await interaction.followup.send(
                    "At least one sanction is required", ephemeral=True
                )
            if len(self.users_sanctioned["reported_users"]) != len(
                self.data["reported_users"]
            ):
                return await interaction.followup.send(
                    "You must add a sanction to all reported users (can be None)",
                    ephemeral=True,
                )
            if self.option_idx:
                self.data["options"][self.option_idx] = self.option
            else:
                self.data["options"].append(self.option)
            await self.bot.db.pollings.update(
                {"_id": self.data["_id"]}, {"options": self.data["options"]}
            )
            for child in self.children:
                child.disabled = True
            try:
                await interaction.edit_original_response(view=self)
            except Exception:
                pass
            await interaction.followup.send("Created Option!", ephemeral=True)


class PollingView(View):
    def __init__(self, bot: PhantomGuard, data: Dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.data = data

    async def interaction_check(self, interaction: Interaction) -> bool:
        if (
            interaction.user.id in self.bot.mods
            or interaction.user.id in self.bot.admins
        ):
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    @button(
        label="Long Description",
        row=0,
        style=discord.ButtonStyle.grey,
        custom_id="POLLING:long_description",
    )
    async def long_description(self, inter: discord.Interaction, btn: discord.Button):
        embed = discord.Embed(
            title="Long Description",
            description=f"{self.data['long_description']}",
            colour=discord.Color.blurple(),
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

    @button(
        label="Attachments",
        row=0,
        style=discord.ButtonStyle.grey,
        custom_id="POLLING:attachments",
    )
    async def show_attachments(self, inter: discord.Interaction, btn: discord.Button):
        await inter.response.defer(ephemeral=True)

        cog = self.bot.get_cog("Reports")

        paginator = AttachmentPaginator(
            None,  # type: ignore
            self.data,
            attachments=cog.reports.format_attachments(self.data["attachments"]),
            viewing_only=True,
        )
        embed = discord.Embed(
            title=f"Attachment's For draft `{self.data['_id']}`. [1/{len(paginator.attachments)}]",
            colour=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{paginator.attachments[0].filename}")
        message = await inter.followup.send(
            embed=embed,
            view=paginator,
            ephemeral=True,
            file=deepcopy(paginator.attachments[0]),
        )
        paginator.original_message = message

    @button(
        label="View Options",
        row=1,
        style=discord.ButtonStyle.grey,
        custom_id="POLLING:view_options",
    )
    async def view_options(self, inter: discord.Interaction, btn: discord.Button):
        if not self.data["options"]:
            return await inter.response.send_message(
                "No options have been created yet!", ephemeral=True
            )
        option = self.data["options"][0]
        embed = discord.Embed(
            title=f"Option 1/{len(self.data['options'])}",
            description=(
                f"**Author**: {option['owner']}\n"
                f"**Addressing Mode**: {option['addressing_type']}\n"
                f"**Attachments**: {' '.join([str(idx) for idx, _ in enumerate(option['attachments'], start=1)])}\n"
                f"**Votes For**: `{floor(option['polling']['points']['for'])}`\n"
                f"**Votes Against**: `{floor(option['polling']['points']['against'])}`\n"
                f"**For**: {', '.join(map(str, option['polling']['users']['for']))}\n"
                f"**Against**: {', '.join(map(str, option['polling']['users']['against']))}"
            ),
        )

        view = OptionsPaginator(self.bot, self.data, view=self)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await inter.original_response()

    @button(
        label="Create Option",
        row=1,
        style=discord.ButtonStyle.grey,
        custom_id="POLLING:create_option",
    )
    async def create_option(self, inter: discord.Interaction, btn: discord.Button):
        view = CreateOptionsView(inter.user.id, self.bot, self.data)
        await inter.response.send_message("Option Manager", view=view, ephemeral=True)


class VerifyReportView(View):
    def __init__(self, bot: PhantomGuard, data: Dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.data = data
        self.points: Dict[str, float] = {"admin": 1.5, "mod": 1.0}
        self.threshold: int = 3

    async def interaction_check(self, interaction: Interaction) -> bool:
        if (
            interaction.user.id in self.bot.mods
            or interaction.user.id in self.bot.admins
        ):
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    @button(
        label="Long Description",
        row=0,
        style=discord.ButtonStyle.grey,
        custom_id="VERIFY:long_description",
    )
    async def long_description(self, inter: discord.Interaction, btn: discord.Button):
        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await inter.response.send_message("This poll has expired.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Long Description",
            description=f"{self.data['long_description']}",
            colour=discord.Color.blurple(),
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

    @button(
        label="Attachments",
        row=0,
        style=discord.ButtonStyle.grey,
        custom_id="VERIFY:attachments",
    )
    async def show_attachments(self, inter: discord.Interaction, btn: discord.Button):
        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await inter.response.send_message("This poll has expired.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        cog = self.bot.get_cog("Reports")

        paginator = AttachmentPaginator(
            None,  # type: ignore
            self.data,
            attachments=cog.reports.format_attachments(self.data["attachments"]),
            viewing_only=True,
        )
        embed = discord.Embed(
            title=f"Attachment's For draft `{self.data['_id']}`. [1/{len(paginator.attachments)}]",
            colour=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{paginator.attachments[0].filename}")
        message = await inter.followup.send(
            embed=embed,
            view=paginator,
            ephemeral=True,
            file=deepcopy(paginator.attachments[0]),
        )
        paginator.original_message = message

    @button(
        label="verify",
        row=1,
        style=discord.ButtonStyle.green,
        custom_id="VERIFY:verify_report",
    )
    async def verify(self, inter: discord.Interaction, btn: discord.Button):
        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await inter.response.send_message("This poll has expired.", ephemeral=True)
            return
        users_voted = self.data["stage1_vote"]["users_for"]
        if inter.user.id in self.bot.admins:
            points = self.points["admin"]
        else:
            points = self.points["mod"]
        if inter.user.id in users_voted:
            await inter.response.send_message(
                "You have already marked this as verified!", ephemeral=True
            )
            return
        elif inter.user.id in self.data["stage1_vote"]["users_against"]:
            self.data["stage1_vote"]["points_against"] -= points
            self.data["stage1_vote"]["users_against"].remove(inter.user.id)
        await inter.response.defer(ephemeral=True)
        self.data["stage1_vote"]["points_for"] += points
        self.data["stage1_vote"]["users_for"].append(inter.user.id)

        update_dict = {"stage1_vote": self.data["stage1_vote"]}
        if self.data["stage1_vote"]["points_for"] >= self.threshold:
            update_dict.update(
                {
                    "stage": 2,
                }
            )
            await inter.edit_original_response(view=PollingView(self.bot, self.data))
            await inter.followup.send(
                "Report has been marked as verified.", ephemeral=True
            )

        await self.bot.db.pollings.update({"_id": self.data["_id"]}, update_dict)
        await inter.followup.send(
            "You have voted to verify the report!", ephemeral=True
        )

    @button(
        label="Delete Report",
        row=1,
        style=discord.ButtonStyle.red,
        custom_id="VERIFY:delete_report",
    )
    async def delete_report(self, inter: discord.Interaction, btn: discord.Button):
        if self.data["expires"].replace(tzinfo=timezone.utc) < discord.utils.utcnow():
            await inter.response.send_message("This poll has expired.", ephemeral=True)
            return
        users_voted = self.data["stage1_vote"]["users_for"]
        if inter.user.id in users_voted:
            await inter.response.send_message(
                "You have already marked this as verified!", ephemeral=True
            )
            return
        await inter.response.defer(ephemeral=True)
        if inter.user.id in self.bot.admins:
            points = self.points["admin"]
        else:
            points = self.points["mod"]

        self.data["stage1_vote"]["points_against"] += points
        update_dict = {"_id": self.data["_id"], "stage1_vote": self.data["stage1_vote"]}
        if self.data["stage1_vote"]["points_against"] >= self.threshold:
            update_dict.update({"stage": 2})
            await self.bot.db.pollings.delete({"_id": self.data["_id"]})
            message = await inter.original_response()
            if message:
                for child in self.children:
                    child.disabled = True
                try:
                    await message.edit(view=self)
                except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                    pass
            self.stop()
            return

        await self.bot.db.pollings.update({"_id": self.data["_id"]}, update_dict)
        await inter.followup.send(
            "You have voted to delete the report!", ephemeral=True
        )


class BasicReportView(View):
    def __init__(self, ctx: Context, data: Dict):
        super().__init__()
        self.ctx = ctx
        self.bot: PhantomGuard = ctx.bot
        self.data = data

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This menu is not for you.", ephemeral=True
        )
        return False

    # @button(label='Long Description', row=0, style=discord.ButtonStyle.grey)
    # async def long_description(self, inter: discord.Interaction, btn: discord.Button):
    #     embed = discord.Embed(
    #         title="Long Description",
    #         description=f"{self.data['long_description']}",
    #         colour=discord.Color.blurple(),
    #     )
    #     await inter.response.send_message(embed=embed, ephemeral=True)

    @button(label="Attachments", row=0, style=discord.ButtonStyle.grey)
    async def show_attachments(self, inter: discord.Interaction, btn: discord.Button):
        await inter.response.defer(ephemeral=True)

        cog = self.bot.get_cog("Reports")

        paginator = AttachmentPaginator(
            None,  # type: ignore
            self.data,
            attachments=cog.reports.format_attachments(self.data["attachments"]),
            viewing_only=True,
        )
        embed = discord.Embed(
            title=f"Attachment's For Report `{self.data['_id']}`. [1/{len(paginator.attachments)}]",
            colour=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{paginator.attachments[0].filename}")
        message = await inter.followup.send(
            embed=embed,
            view=paginator,
            ephemeral=True,
            file=deepcopy(paginator.attachments[0]),
        )
        paginator.original_message = message

    @button(label="View Sanctions", row=0, style=discord.ButtonStyle.red)
    async def view_sanctions(self, inter: discord.Interaction, btn: discord.Button):
        view = SanctionsPaginator(self.bot, self.data["sanctions"], inter.user.id)
        await inter.response.send_message(
            embed=view.sanctions[0], view=view, ephemeral=True
        )
        view.original_message = await inter.original_response()
