from cogs.cog import Cog
from bot.bot import command


class gachiGASM(Cog):
    def __init__(self, bot):
        super().__init__(bot)

    @command()
    async def gachify(self, *, words):
        return await self.bot.say(words.replace(' ', '♂'))


def setup(bot):
    bot.add_cog(gachiGASM(bot))
