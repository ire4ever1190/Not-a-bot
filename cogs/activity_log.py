import asyncio
from datetime import datetime

from discord.activity import ActivityType

from cogs.cog import Cog


class ActivityLog(Cog):
    def __init__(self, bot):
        super(ActivityLog, self).__init__(bot)
        self._db_queue = []
        self._update_task = asyncio.run_coroutine_threadsafe(self._game_loop(), loop=bot.loop)
        self._update_task_checker = asyncio.run_coroutine_threadsafe(self._check_loop(), loop=bot.loop)
        self._update_now = asyncio.Event(loop=bot.loop)

    async def add_game_time(self):
        if not self._db_queue:
            return

        q = self._db_queue
        self._db_queue = []
        await self.bot.dbutils.add_multiple_activities(q)
        del q

    async def _game_loop(self):
        while not self._update_now.is_set():
            try:
                await asyncio.wait_for(self._update_now.wait(), timeout=10, loop=self.bot.loop)
            except asyncio.TimeoutError:
                pass

            if not self._db_queue:
                continue

            try:
                await asyncio.shield(self.add_game_time())
            except asyncio.CancelledError:
                return
            except asyncio.TimeoutError:
                continue

    async def _check_loop(self):
        await asyncio.sleep(120)
        if self._update_task.done():
            self._update_task = self.bot.loop.create_task(self._game_loop())

    @staticmethod
    def status_changed(before, after):
        try:
            if before.activity and before.activity.type == ActivityType.playing and before.activity.start and after.activity is None:
                return True

        # Sometimes you get the error ValueError: year 505XX is out of range
        except ValueError:
            pass

        return False

    async def on_member_update(self, before, after):
        if self.status_changed(before, after):
            self._db_queue.append({'user': after.id,
                                   'time': (datetime.utcnow() - before.activity.start).seconds,
                                   'game': before.activity.name})

    def teardown(self, bot):
        self._update_task_checker.cancel()
        asyncio.run_coroutine_threadsafe(self._update_now.set(), loop=bot.loop)
        try:
            self._update_task.result(timeout=20)
        except TimeoutError:
            pass


def setup(bot):
    bot.add_cog(ActivityLog(bot))
