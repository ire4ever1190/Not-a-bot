import asyncio
import logging
import os
from datetime import timedelta
import dbl

from cogs.cog import Cog

logger = logging.getLogger('debug')


class DBApi(Cog):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot.server.add_listener(self.on_vote)
        self._token = self.bot.config.dbl_token
        self.update_task = None
        self.dbl = None
        if not self.bot.test_mode:
            self.dbl = dbl.Client(self.bot, self._token, loop=bot.loop)
            self.update_task = self.bot.loop.create_task(self.update_stats())

    async def on_vote(self, json):
        s = f'<@{json["user"]}> voted for <@{json["bot"]}>'
        json = {'content': s}
        headers = {'Content-type': 'application/json'}
        await self.bot.aiohttp_client.post(self.bot.config.dbl_webhook, json=json, headers=headers)

    def __unload(self):
        self.bot.server.remove_listener(self.on_vote)
        if self.update_task:
            self.update_task.cancel()

        if self.dbl:
            task = self.bot.loop.create_task(self.dbl.close())
            try:
                task.result(timeout=20)
            except:
                return

    async def update_stats(self):
        while True:
            await asyncio.sleep(3600)
            logger.info('Posting server count')
            try:
                await self.dbl.post_server_count()
                logger.info(f'Posted server count {len(self.bot.guilds)}')
            except Exception as e:
                logger.exception(f'Failed to post server count\n{e}')

            await self._check_votes()

    async def _check_votes(self):
        try:
            botinfo = await self.dbl.get_bot_info(self.bot.user.id)
        except Exception as e:
            logger.exception(f'Failed to get botinfo\n{e}')
            return

        server_specific = self.bot.get_cog('ServerSpecific')
        if not server_specific:
            return

        channel = self.bot.get_channel(339517543989379092)
        if not channel:
            return

        with open(os.path.join(os.getcwd(), 'data', 'votes.txt'), 'r') as f:
            old_votes = int(f.read().strip(' \n\r\t'))

        points = botinfo['points']
        new_votes = points - old_votes
        new_giveaways = new_votes // 10
        if not new_giveaways:
            return

        with open(os.path.join(os.getcwd(), 'data', 'votes.txt'), 'w') as f:
            f.write(str(points - points % 10))

        await server_specific._toggle_every(channel, new_giveaways, timedelta(days=1))


def setup(bot):
    bot.add_cog(DBApi(bot))
