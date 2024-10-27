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


from enum import IntEnum


class Actions(IntEnum):
    NONE: int = 0
    WARN: int = 1
    MUTE: int = 2
    QUARANTINE: int = 3
    KICK: int = 4
    BAN: int = 5

    def __str__(self) -> str:
        if self.value == 0:
            return "none"
        elif self.value == 1:
            return "warn"
        elif self.value == 2:
            return "mute"
        elif self.value == 3:
            return "quarantine"
        elif self.value == 4:
            return "kick"
        elif self.value == 5:
            return "ban"

    def validate(self, value: str) -> bool:
        return str(self) == value

    @staticmethod
    def from_str(value: str) -> "Actions":
        value = value.lower()
        if value == "none":
            return Actions.NONE
        elif value == "warn":
            return Actions.WARN
        elif value == "mute":
            return Actions.MUTE
        elif value == "quarantine":
            return Actions.QUARANTINE
        elif value == "kick":
            return Actions.KICK
        elif value == "ban":
            return Actions.BAN


class AppealActions(IntEnum):
    UNMUTE: int = 1
    UNQUARANTINE: int = 2
    UNBAN: int = 3

    def __str__(self) -> str:
        if self.value == 1:
            return "unmute"
        elif self.value == 2:
            return "unquarantine"
        elif self.value == 3:
            return "unban"


class MaxDuration(IntEnum):
    NONE: int = 0
    WARN: int = 0
    MUTE: int = 28
    QUARANTINE: int = 365
    KICK: int = 0
    BAN: int = 365

    def from_str(value: str) -> "MaxDuration":
        value = value.lower()
        if value == "none":
            return MaxDuration.NONE
        elif value == "warn":
            return MaxDuration.WARN
        elif value == "mute":
            return MaxDuration.MUTE
        elif value == "quarantine":
            return MaxDuration.QUARANTINE
        elif value == "kick":
            return MaxDuration.KICK
        elif value == "ban":
            return MaxDuration.BAN


class ScopeTypes(IntEnum):
    TARGETED: int = 0
    MUTUAL: int = 1
    GLOBAL: int = 2

    def __str__(self) -> str:
        if self.value == 0:
            return "targeted"
        elif self.value == 1:
            return "mutual"
        elif self.value == 2:
            return "global"

    @staticmethod
    def from_str(value: str) -> "ScopeTypes":
        value = value.lower()
        if value == "targeted":
            return ScopeTypes.TARGETED
        elif value == "mutual":
            return ScopeTypes.MUTUAL
        elif value == "global":
            return ScopeTypes.GLOBAL
