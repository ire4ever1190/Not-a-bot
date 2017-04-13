"""
MIT License

Copyright (c) 2017 s0hvaperuna

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import os
from collections import deque, OrderedDict

from discord.ext import commands
from gtts import gTTS

from utils.utilities import split_string
from bot.globals import TTS, SFX_FOLDER

import random


class SFX:
    def __init__(self, name, after_input='', options=''):
        self.name = name
        self.after_input = after_input
        self.before_options = '-nostdin'
        self.options = '-vn -b:a 128k' + options


class Playlist:
    def __init__(self, bot):
        self.voice = None
        self.bot = bot
        self.queue = deque(maxlen=6)
        self.not_empty = asyncio.Event()
        self.next = asyncio.Event()
        self.random_loop = None
        self.sfx_loop = None
        self.player = None
        self.random_sfx_on = self.bot.config.random_sfx

    def on_stop(self):
        self.bot.loop.call_soon_threadsafe(self.next.set)
        return

    def create_tasks(self):
        self.random_loop = self.bot.loop.create_task(self.random_sfx())
        self.sfx_loop = self.bot.loop.create_task(self.audio_player())

    async def random_sfx(self):
        while True:
            users = self.voice.channel.voice_members
            users = list(filter(lambda x: not x.bot, users))
            if not users:
                await self.voice.disconnect()
                self.sfx_loop.cancel()
                break

            if self.random_sfx_on and random.random() < 0.1 and self.voice is not None:

                path = SFX_FOLDER
                files = os.listdir(path)

                sfx = os.path.join(path, random.choice(files))
                if random.random() < 0.5:
                    sfx2 = os.path.join(path, random.choice(files))
                    options = '-i "{}" '.format(sfx2)
                    options += '-filter_complex "[0:a0] [1:a:0] concat=n=2:v=0:a=1 [a]" -map "[a]"'
                    self.add_to_queue(sfx, options)
                else:
                    self.add_to_queue(sfx)

            await asyncio.sleep(60)

    async def audio_player(self):
        while True:
            self.next.clear()
            self.not_empty.clear()
            sfx = self._get_next()
            if sfx is None:
                await self.not_empty.wait()
                sfx = self._get_next()

            self.player = self.voice.create_ffmpeg_player(sfx.name,
                                                          before_options=sfx.before_options,
                                                          after=self.on_stop,
                                                          after_input=sfx.after_input,
                                                          options=sfx.options)

            self.player.start()

            await self.next.wait()

    def is_playing(self):
        if self.voice is None or self.player is None:
            return False

        return not self.player.is_done()

    def add_to_queue(self, entry, after_input=''):
        self.queue.append(SFX(entry, after_input=after_input))
        self.bot.loop.call_soon_threadsafe(self.not_empty.set)

    def add_next(self, entry, options=''):
        self.queue.appendleft(SFX(entry, options))
        self.bot.loop.call_soon_threadsafe(self.not_empty.set)

    def _get_next(self):
        if self.queue:
            return self.queue.popleft()


class Audio:
    def __init__(self, bot, queue):
        self.bot = bot
        self.voice_states = {}
        self.queue = queue

    def get_voice_state(self, server):
        playlist = self.voice_states.get(server.id)
        if playlist is None:
            playlist = Playlist(self.bot)
            self.voice_states[server.id] = playlist

        return playlist

    @commands.command(pass_context=True, no_pm=True, ignore_extra=True, aliases=['summon2'])
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.send_message(ctx.message.channel, 'You are not in a voice channel')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
            state.create_tasks()
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True, ignore_extra=True)
    async def stop_sfx(self, ctx):
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            state.player.stop()

    async def shutdown(self):
        for key in list(self.voice_states.keys()):
            state = self.voice_states[key]
            await self.stop_state(state)
            del self.voice_states[key]

    @staticmethod
    async def stop_state(state):
        if state is None:
            return

        if state.player is not None:
            state.player.stop()

        try:
            if state.sfx_loop is not None:
                state.sfx_loop.cancel()

            if state.voice is not None:
                await state.voice.disconnect()

        except Exception as e:
            print('[ERROR] Error while stopping sfx_bot.\n%s' % e)

    @commands.cooldown(4, 4)
    @commands.command(pass_context=True, no_pm=True)
    async def sfx(self, ctx, *, name):

        path = SFX_FOLDER
        file = self._search_sfx(name)
        if not file:
            return await self.bot.say('Invalid sound effect name')

        file = os.path.join(path, file[0])

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        state.add_to_queue(file)

    @commands.command(name='cadd')
    async def change_combo(self, max_combo=None):
        if max_combo is None:
            return await self.bot.say(self.bot.config.max_combo)
        try:
            max_combo = int(max_combo)
        except ValueError:
            return await self.bot.say('Integer needed')

        self.bot.config.max_combo = max_combo
        await self.bot.say('Max combo set to %s' % str(max_combo))

    @commands.command(name='combo', pass_context=True, no_pm=True, aliases=['concat'])
    async def combine(self, ctx, *, names):
        max_combo = self.bot.config.max_combo
        names = names.split(' ')
        names = list(filter(lambda s: s != '', names))
        if len(names) > max_combo:
            return await self.bot.say('Max %s sfx can be combined' % str(max_combo))

        channel = ctx.message.channel
        silences = []
        silenceidx = 0
        sfx_list = []
        for idx, name in enumerate(names):
            if name.startswith('-') and name != '-':
                silence = name.split('-')[1]
                try:
                    silence = float(silence)
                except ValueError as e:
                    await self.bot.say_timeout('Silence duration needs to be a number\n%s' % e, channel, 90)
                    continue

                silences.append(('aevalsrc=0:d={}[s{}]'.format(silence, str(silenceidx)), idx))
                silenceidx += 1
                continue

            elif name.endswith('-') and name != '-':
                try:
                    bpm = int(''.join(name.split('-')[:-1]))
                    if bpm <= 0:
                        await self.bot.say_timeout('BPM needs to be bigger than 0', channel, 90)
                        continue

                    silence = 60 / bpm
                    silences.append(('aevalsrc=0:d={}[s{}]'.format(silence, str(silenceidx)), idx))
                    silenceidx += 1
                    continue
                except ValueError:
                    pass

            sfx = self._search_sfx(name)
            if not sfx:
                await self.bot.say_timeout("Couldn't find %s. Skipping it" % name, channel, 30)
                continue

            sfx_list += [os.path.join(SFX_FOLDER, sfx[0])]

        if not sfx_list:
            return await self.bot.say_timeout('No sfx found', channel, 30)

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        entry = sfx_list.pop(0)
        if not sfx_list:
            return state.add_to_queue(entry)

        options = ''
        filter_complex = '-filter_complex "'

        for s in silences:
            filter_complex += s[0] + ';'

        audio_order = ['[0:a:0]']
        for idx, sfx in enumerate(sfx_list):
            options += '-i "{}" '.format(sfx)
            audio_order.append('[{}:a:0] '.format(idx + 1))

        for idx, silence in enumerate(silences):
            audio_order.insert(silence[1], '[s{}]'.format(idx))

        filter_complex += ' '.join(audio_order)
        options += filter_complex
        options += 'concat=n={}:v=0:a=1 [a]" -map "[a]"'.format(len(audio_order))
        state.add_to_queue(entry, options)
        'ffmpeg -i audio1.mp3 -i audio2.mp3 -filter_complex "[0:a:0] [1:a:0] concat=n=2:v=0:a=1 [a]" -map "[a]" out.mp3'

    @staticmethod
    def _search_sfx(name):
        name = name.replace(' ', '')
        sfx = sorted(os.listdir(SFX_FOLDER))

        # A very advanced searching algorithm
        file = [x for x in sfx if '.'.join(x.split('.')[:-1]) == name]
        if not file:
            file = [x for x in sfx if '.'.join(x.split('.')[:-1]).startswith(name)]
            if not file:
                file = [x for x in sfx if name in x]

        return file

    @commands.command(pass_context=True, no_pm=True)
    async def random_sfx(self, ctx, value):
        value = value.lower().strip()
        values = {'on': True, 'off': False}
        values_rev = {v: k for k, v in values.items()}

        value = values.get(value, False)
        state = self.get_voice_state(ctx.message.server)
        state.random_sfx_on = value

        await self.bot.say_timeout('Random sfx set to %s' % values_rev.get(value), ctx.message.channel, 120)

    @commands.command(pass_context=True)
    async def sfxlist(self, ctx):
        """List of all the sound effects"""
        sfx = os.listdir(SFX_FOLDER)
        sfx.sort()
        sorted_sfx = OrderedDict()
        curr_add = []
        start = ' '
        for item in sfx:
            if item.startswith(start):
                curr_add += ['__{}__'.format(''.join(item.split('.')[:-1]))]
            else:
                if curr_add:
                    sorted_sfx[start] = curr_add

                curr_add = []
                curr_add += ['__{}__'.format(''.join(item.split('.')[:-1]))]
                start = item[0]

        sorted_sfx = split_string(sorted_sfx, ' **||** ', 1800)
        string = ''
        sfx_str = []
        for items in sorted_sfx:
            for item in items.items():
                string += '**{}**: {}\n'.format(item[0].upper(), item[1])

            sfx_str += [string]
            string = ''

        for string in sfx_str:
            try:
                await self.bot.send_message(ctx.message.channel, string)
            except:
                print(string)

    async def add_sfx(self, ctx):
        if len(ctx.message.attachments) < 1:
            return
        attachments = ctx.message.attachments
        if attachments[0]['size'] > 1000000:
            return

        name = self._get_name(attachments[0]['url'])
        if not name.endswith('.mp3'):
            return await self.bot.say('File needs to be an mp3')

        path_name = os.path.join(SFX_FOLDER, name)
        if os.path.exists(path_name):
            return await self.bot.say('File with the name %s already exist' % name)

        async with self.bot.aiohttp_client.get(attachments[0]['url']) as r:
            if r.status == 200:
                await self.bot.say('Getting file')
                with open(path_name, 'wb') as f:
                    async for chunk in r.content.iter_any():
                        f.write(chunk)

                return await self.bot.say('%s added' % name)
            else:
                return await self.bot.say('Network error %s' % r.status)

    @staticmethod
    def _get_name(url):
        return url.split('/')[-1]

    @commands.command(pass_context=True, no_pm=True, aliases=['stop2'])
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.
        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        await self.stop_state(state)

        del self.voice_states[ctx.message.server.id]

    async def on_join(self, member):
        string = '%s joined the channel' % member.name
        path = os.path.join(TTS, 'join.mp3')
        self._add_tts(path, string, member.server)

    async def on_leave(self, member):
        string = '%s left the channel' % member.name
        path = os.path.join(TTS, 'leave.mp3')
        self._add_tts(path, string, member.server)

    def _add_tts(self, path, string, server):
        gtts = gTTS(string, lang='en-us')
        gtts.save(path)
        state = self.get_voice_state(server)

        state.add_next(path)