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

import re
from typing import TYPE_CHECKING, Dict

import discord
from discord import ButtonStyle, TextStyle
from discord.ui import Modal, TextInput, View, button

from .utils import create_hash

if TYPE_CHECKING:
    from utils.context import Context

    from .impersonation import Impersonation

EMAIL_RE = re.compile(
    r"([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+"
)


class EditQuestionsModal(Modal, title="Edit Security Questions"):
    def __init__(self, view: RegisterView | UpdateView, update_database: bool = False):
        super().__init__()
        self.view: RegisterView | UpdateView = view
        self.update_database: bool = update_database
        self.question_1: TextInput = TextInput(
            label="Question 1",
            default=self.view.question_1,
            style=TextStyle.long,
            placeholder="Question 1...",
            min_length=10,
            max_length=45,
        )
        self.answer_1: TextInput = TextInput(
            label="Answer 1",
            default=self.view.answer_1,
            style=TextStyle.long,
            placeholder="Answer 1...",
            min_length=5,
            max_length=150,
        )
        self.question_2: TextInput = TextInput(
            label="Question 2",
            default=self.view.question_2,
            style=TextStyle.long,
            placeholder="Question 2...",
            min_length=10,
            max_length=45,
            required=False,
        )
        self.answer_2: TextInput = TextInput(
            label="Answer 2",
            default=self.view.answer_2,
            style=TextStyle.long,
            placeholder="Answer 2...",
            min_length=5,
            max_length=150,
            required=False,
        )
        items = [self.question_1, self.answer_1, self.question_2, self.answer_2]
        for item in items:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        questions = {
            "question_1": {self.question_1.value: create_hash(self.answer_1.value)},
            "question_2": None,
        }
        if self.question_2.value and self.answer_2.value:
            questions["question_2"] = {
                self.answer_2.value: create_hash(self.answer_2.value)
            }
        if self.update_database:
            await self.view.ctx.bot.db.impersonation.upsert(
                {"_id": self.view.ctx.author.id},
                {"questions": questions, "enabled": True, "claimed_by": None},
            )
        self.view.question_1 = self.question_1.value
        self.view.answer_1 = self.answer_1.value
        self.view.question_2 = self.question_2.value if self.question_2.value else None
        self.view.answer_2 = self.answer_2.value if self.answer_2.value else None
        if self.update_database:
            self.stop()
        await interaction.followup.send("Security Questions Set!", ephemeral=True)


class SetEmailModal(Modal, title="Edit Email Address"):
    def __init__(self, view: RegisterView):
        super().__init__()
        self.view: RegisterView = view
        self.email: TextInput = TextInput(
            label="Email Address",
            default=self.view.email,
            placeholder="xyz@email.com",
            min_length=10,
            max_length=50,
        )
        self.add_item(self.email)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not re.fullmatch(EMAIL_RE, self.email.value):
            await interaction.response.send_message("Invalid Email!", ephemeral=True)
            return

        self.view.email = self.email.value
        await interaction.response.send_message("Email Set!", ephemeral=True)


class AnswerQuestionsModal(Modal, title="Security Questions"):
    def __init__(self, view: VerifyView):
        super().__init__()
        self.view = view
        self.cog: Impersonation = view.cog
        self.question_1: TextInput = TextInput(
            label=view.question_1,
            style=TextStyle.long,
            placeholder="Answer the question",
            min_length=5,
            max_length=150,
        )
        items = [self.question_1]
        if self.view.question_2:
            self.question_2: TextInput = TextInput(
                label=view.question_2,
                style=TextStyle.long,
                placeholder="Answer the question",
                min_length=5,
                max_length=150,
                required=False,
            )
            items.append(self.question_2)

        for item in items:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.cog.add_request_count(
            interaction.user, self.view.verify_as, self.view.verify_as_email
        )
        if not result:
            await interaction.followup.send(
                "You have tried too many times!", ephemeral=True
            )
            return
        if create_hash(self.question_1.value) != self.view.answer_1:
            await interaction.followup.send("Invalid Answer(s)!", ephemeral=True)
            return

        if self.view.question_2:
            if create_hash(self.question_2.value) != self.view.answer_2:
                await interaction.followup.send("Invalid Answer(s)!", ephemeral=True)
                return

        result = await self.cog.send_otp_email(
            interaction.user, self.view.verify_as, self.view.verify_as_email, "verify"
        )
        if result:
            await interaction.followup.send(
                "An otp code has been sent to your email!", ephemeral=True
            )
            if self.view.verify_as.mutual_guilds:
                try:
                    description = (
                        f"Hello **{self.view.verify_as.name}**\n"
                        f"Your account's questions have been answered by "
                        f"**{interaction.user.name}** (`{interaction.user.id}`)\n"
                        f"As a result a OTP code has been sent to your email for them to verify as you!\n"
                        f"If you did not request this then use `p!verify update` to set new questions"
                    )
                    embed = discord.Embed(
                        title="Security Notice!", description=description
                    )
                    await self.view.verify_as.send(embed=embed)
                except Exception:
                    pass
        else:
            await interaction.followup.send(
                "The email service seems to be down!\nTry again later.", ephemeral=True
            )


class RegisterModal(Modal, title="OTP"):
    def __init__(self, view: RegisterView):
        super().__init__()
        self.view: RegisterView = view
        self.otp_code: TextInput = TextInput(
            label="OTP Code",
            placeholder="The one time password sent to your email!",
            min_length=1,
            max_length=12,
        )
        self.add_item(self.otp_code)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        length = len(self.otp_code.value)
        if length != 9:
            await interaction.response.send_message("Invalid OTP!", ephemeral=True)
            return

        otp_code = self.view.cog.get_otp(interaction.user.id, "register")
        if not otp_code:
            await interaction.response.send_message(
                "OTP code has expired", ephemeral=True
            )
            return

        if otp_code["code"] != self.otp_code.value:
            await interaction.response.send_message("Invalid OTP!", ephemeral=True)
            return

        await interaction.response.defer()

        data = {
            "_id": interaction.user.id,
            "claimed_by": None,
            "questions": {
                "question_1": {self.view.question_1: create_hash(self.view.answer_1)},
            },
            "enabled": True,
            "email": self.view.email,
            "backup_email": None,
        }
        if self.view.question_2 and self.view.answer_2:
            data["questions"]["question2"] = {
                self.view.question_2: create_hash(self.view.answer_2)
            }

        await self.view.ctx.bot.db.impersonation.insert(data)
        self.view.stop()
        await interaction.followup.send("You are now registered!", ephemeral=True)


class RegisterView(View):
    def __init__(self, ctx: Context, cog: Impersonation):
        super().__init__(timeout=480)
        self.ctx: Context = ctx
        self.cog: Impersonation = cog
        self.question_1 = None
        self.answer_1 = None
        self.question_2 = None
        self.answer_2 = None
        self.email = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("This is not for you", ephemeral=True)
        return False

    @button(label="Questions", style=ButtonStyle.green)
    async def questions(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        await interaction.response.send_modal(EditQuestionsModal(self))

    @button(label="Email", style=ButtonStyle.blurple)
    async def email(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        await interaction.response.send_modal(SetEmailModal(self))

    @button(label="Send OTP", style=ButtonStyle.red)
    async def send_register_code(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        if not self.email:
            await interaction.response.send_message(
                "You need to set an email!", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        otp = self.cog.get_otp(interaction.user.id, "register")
        if otp:
            await interaction.followup.send(
                f"OTP was already sent and expires {discord.utils.format_dt(otp['expires'], 'R')}",
                ephemeral=True,
            )
            return
        result = await self.cog.send_otp_email(
            interaction.user, interaction.user, self.email, "register"
        )
        if result:
            await interaction.followup.send(
                "An otp code has been sent to your email!", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "The email service seems to be down!\nTry again later.", ephemeral=True
            )

    @button(label="Register", style=ButtonStyle.green)
    async def register(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        if not self.email:
            await interaction.response.send_message(
                "You need to set an email!", ephemeral=True
            )
            return
        if not self.question_1 and self.answer_1:
            await interaction.response.send_message(
                "You need to have at least 1 security question!", ephemeral=True
            )
            return
        await interaction.response.send_modal(RegisterModal(self))


class VerifyModal(Modal, title="Enter OTP"):
    def __init__(self, view: VerifyView):
        super().__init__()
        self.view = view
        self.otp_code: TextInput = TextInput(
            label="OTP Code",
            placeholder="The one time password sent to your email!",
            min_length=1,
            max_length=12,
        )
        self.add_item(self.otp_code)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        length = len(self.otp_code.value)
        if length != 9:
            await interaction.response.send_message("Invalid OTP!", ephemeral=True)
            return

        otp_code = self.view.cog.get_otp(self.view.verify_as.id, "verify")
        if not otp_code:
            await interaction.response.send_message(
                "OTP code has expired", ephemeral=True
            )
            return

        if otp_code["code"] != self.otp_code.value:
            await interaction.response.send_message("Invalid OTP!", ephemeral=True)
            return

        await interaction.response.defer()

        data = {"_id": self.view.verify_as.id, "claimed_by": interaction.user.id}
        await self.view.ctx.bot.db.impersonation.upsert(
            {"_id": self.view.verify_as.id}, data
        )
        if self.view.verify_as.mutual_guilds:
            try:
                description = (
                    f"Hello {self.view.verify_as.name}\n"
                    f"Your account has been linked with **{interaction.user.name}** (`{interaction.user.id}`).\n"
                    f"If you did not request this please run `p!verify update` to secure your identity!"
                )
                embed = discord.Embed(title="Security Notice!", description=description)
                await self.view.verify_as.send(embed=embed)
            except Exception:
                pass
        self.view.stop()
        await interaction.followup.send(
            f"You are now verified as {self.view.verify_as.name}!", ephemeral=True
        )


class VerifyView(View):
    def __init__(
        self,
        ctx: Context,
        verify_as: discord.Member | discord.User,
        cog: Impersonation,
        data: Dict,
    ):
        super().__init__()
        self.ctx: Context = ctx
        self.verify_as: discord.Member | discord.User = verify_as
        self.cog: Impersonation = cog
        self.data = data
        self.question_1 = None
        self.answer_1 = None
        self.question_2 = None
        self.answer_2 = None
        self.verify_as_email = data["email"]
        for question_num in data["questions"]:
            if not data["questions"][question_num]:
                continue
            for question in data["questions"][question_num]:
                if question_num == "question_1":
                    self.question_1 = question
                    self.answer_1 = data["questions"][question_num][question]
                if question_num == "question_2":
                    self.question_2 = question
                    self.answer_2 = data["questions"][question_num][question]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("This is not for you", ephemeral=True)
        return False

    @button(label="Questions", style=ButtonStyle.blurple)
    async def answer_questions(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        await interaction.response.send_modal(AnswerQuestionsModal(self))

    @button(label="Verify Code", style=ButtonStyle.green)
    async def verify_code(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        await interaction.response.send_modal(VerifyModal(self))


class UpdateView(View):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.question_1 = None
        self.answer_1 = None
        self.question_2 = None
        self.answer_2 = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("This is not for you", ephemeral=True)
        return False

    @button(label="Questions", style=ButtonStyle.blurple)
    async def update_questions(
        self, interaction: discord.Interaction, btn: discord.Button
    ) -> None:
        await interaction.response.send_modal(
            EditQuestionsModal(self, update_database=True)
        )
