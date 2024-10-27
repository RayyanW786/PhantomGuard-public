import asyncio
from collections.abc import MutableMapping
from datetime import datetime, timedelta, timezone

from utils.time import human_timedelta


class TimedValue:
    def __init__(self, value, expires, task):
        self.value: any = value
        self.expires: datetime = expires
        self.task: asyncio.Task = task


class AsyncTimedCache(MutableMapping):
    def __init__(self, *, timeout=600, loop=None):
        self.timeout, _ = self._make_delays(timeout)
        self.loop = loop
        self.storage = {}

    def _make_delays(self, delay):
        dt_now = datetime.now(tz=timezone.utc)

        if isinstance(delay, timedelta):
            return delay.total_seconds(), (dt_now + delay)

        if isinstance(delay, datetime):
            delta = dt_now - delay.replace(tzinfo=timezone.utc)
            return delta.total_seconds, delay

        if isinstance(delay, int):
            final_delay = delay or self.timeout
            return final_delay, (dt_now + timedelta(seconds=final_delay))

        elif delay is None:
            return self.timeout

        raise TypeError(
            f"Expected (timedelta, datetime, int, None), got ({delay.__class__.__name__})"
        )

    async def _timed_del(self, key, timeout):
        self.storage.pop(await asyncio.sleep(timeout or self.timeout, result=key))

    def __setitem__(self, key, value, *, timeout=None):
        previous_value = self.storage.pop(key, None)
        if previous_value:
            previous_value.task.cancel()

        timeout, final = self._make_delays(timeout)
        coro = self._timed_del(key, timeout=timeout)
        task = self.loop.create_task(coro, name="Timed deletion")
        self.storage[key] = TimedValue(value=value, expires=final, task=task)

    def __getitem__(self, key):
        return self.storage[key]

    def __delitem__(self, key):
        self.storage[key].task.cancel()
        del self.storage[key]

    def __iter__(self):
        return iter(self.storage)

    def __len__(self):
        return len(self.storage)

    def __repr__(self):
        return repr(self.storage)

    def __str__(self):
        return str({k: v for k, v in self._clean_keys()})

    def __eq__(self, value):
        return self.storage == value

    def __bool__(self):
        return bool(self.storage)

    def __del__(self):
        for key in self.storage.keys():
            del self.storage[key]

    def _clean_keys(self):
        dt_now = datetime.now(tz=timezone.utc)
        for key, timedvalue in self.storage.items():
            yield (
                key,
                (
                    timedvalue,
                    f"Expires in {human_timedelta(dt_now - timedvalue.expires)}",
                ),
            )

    def get(self, key, default):
        timed_value = self.storage.get(key, default)
        return getattr(timed_value, "value", default)

    def set(self, key, value, timeout):
        self.__setitem__(key, value, timeout=timeout)
        return value
