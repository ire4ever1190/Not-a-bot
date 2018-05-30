import logging

import discord
from discord.ext.commands import cooldown, BucketType
from sqlalchemy import text
from sqlalchemy.dialects import mysql
from bot.converters import PossibleUser
from sqlalchemy.exc import SQLAlchemyError

from bot.bot import command
from cogs.cog import Cog
from utils.utilities import check_user_mention

logger = logging.getLogger('debug')
terminal = logging.getLogger('terminal')


class Stats(Cog):
    def __init__(self, bot):
        super().__init__(bot)

    @command(no_pm=True)
    @cooldown(2, 5, type=BucketType.guild)
    async def mention_stats(self, ctx, page=None):
        """Get stats on how many times which roles are mentioned on this server"""
        guild = ctx.guild

        if page is not None:
            try:
                # No one probably hasn't created this many roles
                if len(page) > 6:
                    return await ctx.send('Page out of range')

                page = int(page)
                if page <= 0:
                    page = 1
            except:
                page = 1
        else:
            page = 1

        sql = 'SELECT * FROM `mention_stats` WHERE guild={} ORDER BY amount DESC LIMIT {}'.format(guild.id, 10*page)
        rows = (await self.bot.dbutil.execute(sql)).fetchall()
        if not rows:
            return await ctx.send('No role mentions logged on this server')

        embed = discord.Embed(title='Most mentioned roles in server {}'.format(guild.name))
        added = 0
        p = page*10
        for idx, row in enumerate(rows[p-10:p]):
            added += 1
            role = self.bot.get_role(row['role'], guild)
            if role:
                role_name, role = role.name, role.id
            else:
                role_name, role = row['role_name'], row['role']

            embed.add_field(name='{}. {}'.format(idx + p-9, role),
                            value='<@&{}>\n{}\nwith {} mentions'.format(role, role_name, row['amount']))

        if added == 0:
            return await ctx.send('Page out of range')

        await ctx.send(embed=embed)

    @command(aliases=['seen'])
    @cooldown(1, 5, BucketType.user)
    async def last_seen(self, ctx, user: PossibleUser):
        """Get when a user was last seen"""

        if isinstance(user, discord.User):
            user_id = user.id
            username = str(user)
        elif isinstance(user, int):
            user_id = user
            username = None
        else:
            user_id = None
            username = user

        guild = ctx.guild
        if guild is not None:
            guild = guild.id
            sql = 'SELECT * FROM `last_seen_users` WHERE (guild=0 OR guild=:guild) AND '
        else:
            guild = 0
            sql = 'SELECT * FROM `last_seen_users` WHERE guild=0 AND'

        if user_id:
            sql += 'user=:user ORDER BY last_seen DESC LIMIT 2'
        else:
            sql += 'username=:user ORDER BY last_seen DESC LIMIT 2'

        session = self.bot.get_session
        try:
            rows = session.execute(sql, {'guild': guild, 'user': user_id or username}).fetchall()
        except SQLAlchemyError:
            terminal.exception('Failed to get last seen from db')
            return await ctx.send('Failed to get user because of an error')

        if len(rows) == 0:
            return await ctx.send("No users found with {}. Either the bot hasn't had the chance to log activity or the name was wrong."
                                  "Names are case sensitive and must include the discrim".format(username))
        local = None
        global_ = None

        for row in rows:
            if row['guild'] == 0:
                global_ = row

            else:
                local = row

        if user_id is None:
            if local:
                user_id = local['user']
            else:
                user_id = global_['user']

        if username is None:
            username = local['username']

        msg = 'User {} `{}`\n'.format(username, user_id)
        if local:
            msg += 'Last seen on this server {} UTC\n'.format(local['last_seen'])
        if global_:
            msg += 'Last seen elsewhere {} UTC'.format(global_['last_seen'])

        await ctx.send(msg)


def setup(bot):
    bot.add_cog(Stats(bot))
