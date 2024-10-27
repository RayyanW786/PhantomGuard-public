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
import logging
import os
import random
import string
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, AnyStr, Dict, Literal, Optional, TypedDict

import aiosmtplib
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.checks import custom_check
from utils.time import human_timedelta

from .views import RegisterView, UpdateView, VerifyView

if TYPE_CHECKING:
    from bot import PhantomGuard
    from utils.context import Context

load_dotenv()
log = logging.getLogger(__name__)


class RequestCache(TypedDict):
    """One Time Password Cache"""

    tries: int
    expires: datetime  # 15 minutes


class OTPCache(TypedDict):
    code: str
    expires: datetime  # 5 minutes


class Impersonation(commands.Cog):
    """Prevents users from impersonating staff / other users"""

    def __init__(self, bot: PhantomGuard) -> None:
        self.__bot = bot
        self.__request_cache: Dict[str, RequestCache] = {}
        # str key = {requested_by.id}-{verify_as.id}
        self.__limit: int = 3
        self.__sender_email: str = os.getenv("EMAIL_ADDRESS")
        self.__sender_password: str = os.getenv("EMAIL_APP_PASSWORD")
        self.__smtp_client: Optional[aiosmtplib.SMTP] = None
        self.__register_otp: Dict[int, OTPCache] = {}
        self.__verify_otp: Dict[int, OTPCache] = {}
        self.__otp_length: int = 9
        self.__otp_expires_minutes: int = 5
        self.__printable: AnyStr = "".join(
            [string.ascii_letters, string.punctuation, string.digits]
        )
        asyncio.create_task(self.clear_cache())

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="elem_blocked", id=1133488854402347120)

    async def clear_cache(self) -> None:
        while True:
            for request, data in self.__request_cache.copy().items():
                if data["expires"] < discord.utils.utcnow():
                    del self.__request_cache[request]

            for user, otp in self.__register_otp.copy().items():
                if otp["expires"] < discord.utils.utcnow():
                    del self.__register_otp[user]

            for user, otp in self.__verify_otp.copy().items():
                if otp["expires"] < discord.utils.utcnow():
                    del self.__verify_otp[user]

            await asyncio.sleep(60)

    async def cog_load(self) -> None:
        self.__smtp_client = aiosmtplib.SMTP(
            hostname="smtp.gmail.com", port=587, start_tls=True
        )
        await self.__smtp_client.connect()
        await self.__smtp_client.login(self.__sender_email, self.__sender_password)

    async def cog_unload(self) -> None:
        if self.__smtp_client and self.__smtp_client.is_connected():
            await self.__smtp_client.quit()

    def generate_otp(
        self, user_id: int, reason: Literal["register", "verify"]
    ) -> OTPCache:
        if reason == "verify" and user_id in self.__verify_otp:
            return self.get_otp(user_id, reason)
        if reason == "register" and user_id in self.__register_otp:
            return self.get_otp(user_id, reason)
        otp_code = "".join(
            random.SystemRandom().choices(self.__printable, k=self.__otp_length)
        )
        data: OTPCache = {
            "code": otp_code,
            "expires": discord.utils.utcnow()
            + timedelta(minutes=self.__otp_expires_minutes),
        }
        if reason == "verify":
            self.__verify_otp[user_id] = data
        elif reason == "register":
            self.__register_otp[user_id] = data
        return data

    def get_otp(
        self, user_id: int, reason: Literal["register", "verify"]
    ) -> Optional[OTPCache]:
        result = None
        if reason == "verify":
            result = self.__verify_otp.get(user_id)
        if reason == "register":
            result = self.__register_otp.get(user_id)
        if result:
            if result["expires"] <= discord.utils.utcnow():
                del self.__verify_otp[user_id]
                return
            return result
        return

    async def add_request_count(
        self,
        requested_by: discord.Member | discord.User,
        verify_as: discord.Member | discord.User,
        verify_as_email: str,
    ) -> bool:
        key = f"{requested_by.id}-{verify_as.id}"
        if self.__request_cache[key]["tries"] + 1 > self.__limit:
            await self.invalidate_account(requested_by, verify_as, verify_as_email)
            return False
        self.__request_cache[key]["tries"] += 1
        return True

    async def invalidate_account(
        self,
        requested_by: discord.Member | discord.User,
        verify_as: discord.Member | discord.User,
        verify_as_email: str,
    ) -> None:
        """
        Called when someone gets more than self.__limit tries on their account
        This function invalidates their account for verification and emails them!
        """
        # bot ban requested_by
        await self.__bot.blacklist.add_to_blacklist(
            requested_by.id,
            "user",
            f"tried to impersonate {verify_as.name} ({verify_as.id}.id)",
        )
        # user_id's enabled = False & set questions to None
        await self.__bot.db.impersonation.upsert(
            {
                "_id": verify_as.id,
            },
            {"questions": None, "enabled": False},
        )
        # send user an email
        if verify_as.mutual_guilds:
            try:
                description = (
                    f"Hello **{verify_as.name}**\n"
                    f"Your account has been **prone** to an **impersonation attack** by "
                    f"**{requested_by.name}** (`{requested_by.id}`)!\n"
                    f"As a result you will need to set a question, "
                    f"for security reasons your current one has been __removed__!\n"
                    f"Use `p!verify update` to set new questions"
                )
                embed = discord.Embed(title="Security Notice!", description=description)
                await verify_as.send(embed=embed)
            except Exception:
                pass
        # send user a email
        await self.send_otp_email(
            requested_by, verify_as, verify_as_email, "invalidate"
        )

    async def send_otp_email(
        self,
        requested_by: discord.Member | discord.User,
        verify_as: discord.Member | discord.User,
        email: str,
        reason: Literal["register", "verify", "invalidate"],
    ) -> bool:
        if not self.__smtp_client:
            return False
        """Sends the OTP code to the provided email address using Gmail's SMTP server."""
        subject = "Authentication Code [ Phantom Guard ]"
        if reason == "verify":
            otp_code = self.generate_otp(verify_as.id, "verify")
            body = (
                f"Hello {verify_as.name}\n"
                f"Your One Time Password is: {otp_code['code']}\n"
                f"This code will expire in {human_timedelta(otp_code['expires'])}.\n\n"
                f"This code was requested by {requested_by.name} ({requested_by.id})!\n"
                f"Note: You will need to set a new question, for security reasons your current one has been removed!"
            )
        elif reason == "register":
            otp_code = self.generate_otp(verify_as.id, "register")
            body = (
                f"Hello {verify_as.name}\n"
                f"Your One Time Password is: {otp_code['code']}\n"
                f"This code will expire in {human_timedelta(otp_code['expires'])}.\n\n"
                f"Thank you for choosing Phantom Guard!"
            )
        elif reason == "invalidate":
            body = (
                f"Hello {verify_as.name}\n"
                f"Your account has been prone to an impersonation attack by {requested_by.name} ({requested_by.id})!\n"
                f"As a result you will need to set a question, for security reasons your current one has been removed!"
                f"\nUse p!verify update to set new questions"
            )
        message = MIMEText(body)
        message["Subject"] = subject
        message["From"] = self.__sender_email
        message["To"] = email

        try:
            if not self.__smtp_client.is_connected:
                if (
                    self.__smtp_client._connect_lock
                    and self.__smtp_client._connect_lock.locked()
                ):
                    self.__smtp_client.close()
                log.warning("207, smtp closed")
                await self.__smtp_client.connect()
                log.info("209 smtp connected")
            await self.__smtp_client.send_message(message)
        except aiosmtplib.SMTPException:
            if not self.__smtp_client.is_connected:
                if (
                    self.__smtp_client._connect_lock
                    and self.__smtp_client._connect_lock.locked()
                ):
                    self.__smtp_client.close()
                log.warning("215, smtp closed")
                await self.__smtp_client.connect()
                log.info("217, smtp connected")
            await self.__smtp_client.login(self.__sender_email, self.__sender_password)

            # Retry sending the email
            try:
                await self.__smtp_client.send_message(message)
            except Exception:
                return False
        return True

    @custom_check()
    @commands.hybrid_group("verify", invoke_without_command=True)
    async def verify(self, ctx: Context) -> None:
        """Commands related to verifying your identity"""
        await ctx.send_help("verify")

    @custom_check()
    @verify.command(name="register")
    async def verify_register(self, ctx: Context) -> None:
        """Register your account under this impersonation protection system!"""
        # check if user is registered!
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        found = await self.__bot.db.impersonation.find({"_id": ctx.author.id})
        if found:
            if found["enabled"]:
                await ctx.reply(
                    "Your account is already registered!\nUse `p!verify delete` to unregister",
                    ephemeral=True,
                )
                return
            else:
                await ctx.reply(
                    "Your account is automatically de-listed until you update your questions!\nUse `p!verify update`"
                )
        view = RegisterView(ctx, self)
        await ctx.reply(
            "Register your account under this impersonation protection system!",
            view=view,
            ephemeral=True,
        )

    @custom_check()
    @verify.command(name="update")
    async def verify_update(self, ctx: Context) -> None:
        """Update your questions"""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        found = await self.__bot.db.impersonation.find({"_id": ctx.author.id})
        if not found:
            await ctx.reply(
                "Your account is not registered!\nUse `p!verify register` to register",
                ephemeral=True,
            )
            return
        view = UpdateView(ctx)
        await ctx.reply("Update your questions!", view=view, ephemeral=True)

    @custom_check()
    @verify.command(name="delete")
    async def verify_delete(self, ctx: Context) -> None:
        """Deletes all of your registered data!"""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()

        value = await ctx.prompt("Are you sure you want to delete your data?")
        if not value:
            return
        else:
            deleted = await self.__bot.db.impersonation.delete({"_id": ctx.author.id})
            if deleted:
                await ctx.reply("Deleted your data!", ephemeral=True)
            else:
                await ctx.reply(
                    "You are not registered, there is nothing for me to delete!",
                    ephemeral=True,
                )

    @custom_check()
    @verify.command(name="as")
    async def verify_as(
        self, ctx: Context, user: discord.Member | discord.User
    ) -> None:
        """Verify your identity as another user!"""
        if ctx.author.id == user.id:
            await ctx.reply("You cannot verify as yourself LOL", ephemeral=True)
            return
        if ctx.interaction:
            await ctx.defer()
        else:
            await ctx.typing()
        found = await self.__bot.db.impersonation.find({"_id": user.id})
        if not found:
            await ctx.reply(f"{user.name} is not registered!", ephemeral=True)
            return
        if found["claimed_by"]:
            await ctx.reply(
                f"This account is linked to <@{found['claimed_by']}>",
            )
            return
        if not found["enabled"]:
            await ctx.reply(
                f"{user.name} account is locked due to security concerns!",
                ephemeral=True,
            )
            return

        exists = self.__request_cache.get(f"{ctx.author.id}-{user.id}")
        if (
            exists
            and exists["tries"] >= 3
            and exists["expires"] > discord.utils.utcnow()
        ):
            await ctx.reply(
                f"You have tried to verify as {user.name} too many times!",
                ephemeral=True,
            )
            return

        if not exists:
            self.__request_cache[f"{ctx.author.id}-{user.id}"] = {
                "tries": 0,
                "expires": discord.utils.utcnow() + timedelta(minutes=15),
            }

        view = VerifyView(ctx, user, self, found)
        await ctx.reply(f"Verify as {user.name}", view=view, ephemeral=True)
