# LICENSE: https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt

# This file includes portions from RoboDanny, licensed under MPL-2.0
# Modifications and additions copyright (c) 2024-present Rayyan

import copy
import io
import sys
import textwrap
import time
import traceback
from contextlib import redirect_stdout
from typing import Any, Optional, Union

import discord
from discord.ext import commands, menus
from discord.ext.commands import Context

nl = "\n"


class EvalPages(discord.ui.View):
    # [code omitted]
    ...


class EvalPageSource(menus.ListPageSource):
    # [code omitted]
    ...


class Developer(commands.Cog):
    """developer related commands!"""

    def __init__(self, bot):
        self.bot = bot
        self._last_result: Optional[Any] = None

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="element_dev", id=1198596484237639701)

    @commands.hybrid_group(invoke_without_subcommand=True)
    async def owner(self, ctx: Context):
        await ctx.send_help(ctx)

    @owner.command(name="add")
    async def admin_add(self, ctx: Context, user: discord.Member | discord.User):
        if user.id in self.bot.admins:
            return await ctx.reply(f"{user.mention} is already a bot admin.")
        else:
            self.bot.admins.append(user.id)
            await ctx.bot.db.admins.insert(
                {
                    "_id": user.id,
                }
            )
            await ctx.reply(f"{user.mention} is now a bot admin.")

    @owner.command(name="remove")
    async def admin_remove(self, ctx: Context, user: discord.Member | discord.User):
        if user.id not in self.bot.admins:
            return await ctx.reply(f"{user.mention} is not a bot admin.")
        else:
            self.bot.admins.remove(user.id)
            await ctx.bot.db.admins.delete(
                {
                    "_id": user.id,
                }
            )
            await ctx.reply(f"{user.mention} is no longer a bot admin.")

    async def cog_check(self, ctx: Context):
        if await self.bot.is_owner(ctx.author):
            return True
        else:
            raise commands.NotOwner()

    def cleanup_code(self, content: str):
        """Automatically removes code blocks from the code."""
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])
        return content

    @commands.command("load")
    async def load(self, ctx: Context, extension: str):
        """Loads a bot's extension."""
        await self.bot.load_extension(f"cogs.{extension}")
        await ctx.send(f"Loaded extension `{extension}`")

    @commands.command("unload")
    async def unload(self, ctx: Context, extension: str):
        """Unloads a bot's extension."""
        await self.bot.unload_extension(f"cogs.{extension}")
        await ctx.send(f"Unloaded extension `{extension}`")

    @commands.command("reload")
    async def reload(self, ctx: Context, extension: str):
        """Reloads a bot's extension."""
        await self.bot.reload_extension(f"cogs.{extension}")
        await ctx.send(f"Reloaded extension `{extension}`")

    @commands.command("eval", aliases=["e", "py", "python"])
    async def eval(self, ctx: Context, *, code: str):
        """Direct evaluation of Python code."""
        async with ctx.typing():
            env = {
                "b": self.bot,
                "c": ctx,
                "s": ctx.send,
                "r": ctx.reply,
                "chan": ctx.channel,
                "auth": ctx.author,
                "g": ctx.guild,
                "msg": ctx.message,
                "_": self._last_result,
            }
            env.update(globals())
            start_time = time.monotonic()

            code = self.cleanup_code(code)
            stdout = io.StringIO()

            to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'

            version = f'Python {sys.version.replace(nl, " ")}'
            value = None
            ret = None

            try:
                exec(to_compile, env)
            except Exception as e:
                value = e.__class__.__name__ + ": " + str(e)
                ret = type(e)

            if value is None:
                func = env["func"]
                try:
                    with redirect_stdout(stdout):
                        ret = await func()
                except Exception as e:
                    value = stdout.getvalue() + traceback.format_exc()
                    ret = type(e)

            if value is None:
                value = stdout.getvalue()

            total_time = time.monotonic() - start_time

            try:
                await ctx.message.add_reaction("\u2705")
            except:
                pass

            if ret is not None:
                self._last_result = ret

            pages = EvalPages(
                EvalPageSource(
                    version=version, result_time=total_time, ret=ret, stdout=value
                ),
                ctx=ctx,
            )
            await pages.start()

    @commands.command("exec", aliases=["sudo"])
    async def exec(
        self,
        ctx: Context,
        channel: Optional[discord.TextChannel],
        user: Union[discord.Member, discord.User],
        *,
        command: str,
    ):
        """Run a command as another user optionally in another channel."""
        msg = copy.copy(ctx.message)
        msg.channel = channel or ctx.channel
        msg.author = user
        msg.content = f"{ctx.prefix}{command}"
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        await self.bot.invoke(new_ctx)
        await ctx.message.add_reaction("\u2705")

    @commands.command("repeat")
    async def repeat(self, ctx: Context, times: Optional[int] = 1, *, command: str):
        """Repeats a command a specified number of times."""
        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        await ctx.message.add_reaction("▶️")
        try:
            await new_ctx.reinvoke()
        except ValueError:
            return await ctx.send(f'No command called "{command}" found.')
        for x in range(times - 1):
            await new_ctx.reinvoke()
        await ctx.message.add_reaction("\u2705")

    @commands.command("maintenance")
    async def maintenance(self, ctx: Context, option: bool) -> None:
        ctx.bot.maintenance = option
        await ctx.send(f"set maintenance mode to {option}")


async def setup(bot):
    await bot.add_cog(Developer(bot))
