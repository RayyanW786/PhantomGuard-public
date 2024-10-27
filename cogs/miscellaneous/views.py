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
from discord.ui import Modal, TextInput, View, button

if TYPE_CHECKING:
    from utils.context import Context


class EditUserProfile(Modal, title="Edit User Profile"):
    def __init__(self, view: UserProfileView) -> None:
        super().__init__()
        self.view: UserProfileView = view
        self.resume: TextInput = TextInput(
            label="Resume",
            style=discord.TextStyle.long,
            placeholder="Let people know what you have achieved",
            default=self.view.resume,
            max_length=4000,
            required=False,
        )
        self.for_hire: TextInput = TextInput(
            label="Hire Me",
            style=discord.TextStyle.long,
            placeholder="Let people know you want to be hired and for what positions",
            default=self.view.for_hire,
            max_length=4000,
            required=False,
        )
        self.add_item(self.resume)
        self.add_item(self.for_hire)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        to_update = {
            "resume": self.resume.value,
            "for_hire": self.for_hire.value or None,
        }
        self.view.resume = self.resume.value
        self.view.for_hire = self.for_hire.value
        await self.view.ctx.bot.db.user_profile.upsert(
            {
                "_id": interaction.user.id,
            },
            to_update,
        )
        await interaction.followup.send("updated user profile", ephemeral=True)


class UserProfileView(View):
    def __init__(
        self,
        ctx: Context,
        user: discord.User,
        resume: Optional[str],
        for_hire: Optional[str],
    ) -> None:
        super().__init__()
        self.ctx: Context = ctx
        self.user: discord.User = user
        self.resume: Optional[str] = resume
        self.for_hire: Optional[str] = for_hire

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.ctx.author.id == interaction.user.id:
            return True
        await interaction.response.send_message(
            "This menu cannot be controlled by you", ephemeral=True
        )
        return False

    @button(label="Resume", style=discord.ButtonStyle.blurple)
    async def resume_btn(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        if self.ctx.author.id == self.user.id:
            await interaction.response.send_modal(EditUserProfile(self))
        else:
            if self.user.id in interaction.client.blacklist.users:
                await interaction.response.send_message(
                    f"{self.user.name} is bot banned!", ephemeral=True
                )
                return
            if self.resume is not None:
                embed = discord.Embed(title="Resume", description=self.resume)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"{self.user.name} has not set a resume yet.", ephemeral=True
                )

    @button(label="Hire Me", style=discord.ButtonStyle.blurple)
    async def hire_me(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        if self.ctx.author.id == self.user.id:
            await interaction.response.send_modal(EditUserProfile(self))
        else:
            if self.user.id in interaction.client.blacklist.users:
                await interaction.response.send_message(
                    f"{self.user.name} is bot banned!", ephemeral=True
                )
                return
            if self.for_hire is not None:
                embed = discord.Embed(title="Hire Me", description=self.for_hire)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"{self.user.name} has not set a for hire yet.", ephemeral=True
                )
