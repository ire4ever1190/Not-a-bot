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
import logging
import os

logger = logging.getLogger('debug')


class Song:
    __slots__ = ['title', 'url', 'webpage_url', 'id', 'duration', 'uploader',
                 'playlist', 'seek', 'success', 'filename', 'before_options',
                 'options', 'dl_folder', '_downloading', 'on_ready', 'player',
                 'logger', 'bpm', 'config']

    def __init__(self, playlist=None, filename=None, config=None, **kwargs):
        self.title = kwargs.pop('title', 'Untitled')
        self.url = kwargs.pop('url', 'None')
        self.webpage_url = kwargs.pop('webpage_url', None)
        self.id = kwargs.pop('id', None)
        self.duration = kwargs.pop('duration', 0)
        self.uploader = kwargs.pop('uploader', 'None')
        self.playlist = playlist
        self.seek = False
        self.success = False
        self.config = config
        self.filename = filename
        self.before_options = kwargs.pop('before_options', '')
        if '-nostdin' not in self.before_options:
            self.before_options = ' '.join(('-nostdin', self.before_options)).strip()

        self.options = kwargs.pop('options', '')
        if '-vn -b:a' not in self.options:
            self.options = ' '.join((self.options, '-vn -b:a 128k')).strip()

        self.dl_folder = self.playlist.downloader.dl_folder
        self._downloading = False
        self.on_ready = asyncio.Event()
        self.player = None
        self.bpm = None

    @classmethod
    def from_song(cls, song):
        s = Song(**{k: getattr(song, k, None) for k in song.__slots__})
        s.filename = song.filename
        s.bpm = song.bpm
        return s

    def __str__(self):
        string = '**{0.title}**'
        return string.format(self)

    def long_str(self):
        string = '**{0.title}** uploaded by {0.uploader}'
        return string.format(self)

    def info_from_dict(self, **kwargs):
        self.title = kwargs.pop('title', self.title)
        self.url = kwargs.pop('url', self.url)
        self.webpage_url = kwargs.pop('webpage_url', self.webpage_url)
        self.id = kwargs.pop('id', self.id)
        self.duration = kwargs.pop('duration', self.duration)
        self.uploader = kwargs.pop('uploader', self.uploader)
        self.before_options = kwargs.pop('before_options', self.before_options)
        self.options = kwargs.pop('options', self.options)

    async def download(self):
        if self._downloading or self.success:
            return

        self._downloading = True
        logger.debug('Started downloading %s' % self.long_str())
        try:
            dl = self.config.download
            loop = self.playlist.bot.loop
            if dl:
                if not os.path.exists(self.dl_folder):
                    print('[INFO] Making directory %s' % self.dl_folder)
                    os.makedirs(self.dl_folder)
                    logger.debug('Created dir {}'.format(self.dl_folder))

                if self.filename is not None and os.path.exists(self.filename):
                    self.success = True
                    return

                check_dl = False
                if self.id is not None:
                    fdir = os.listdir(self.dl_folder)
                    for f in fdir:
                        if self.id in f:
                            check_dl = True
                            break

                if check_dl and self.filename is None:
                    logger.debug('Getting and checking info for: {}'.format(self))
                    info = await self.playlist.downloader.safe_extract_info(loop, url=self.webpage_url, download=False)
                    logger.debug('Got info')
                    self.filename = self.playlist.downloader.safe_ytdl.prepare_filename(info)
                    logger.debug('Filename set to {}'.format(self.filename))

                if self.filename is not None:
                    if os.path.exists(self.filename):
                        print('[INFO] File exists for %s' % self.title)
                        logger.debug('File exists for %s' % self.title)
                        self.success = True
                        return

            logger.debug('Getting info and downloading {}'.format(self.webpage_url))
            info = await self.playlist.downloader.extract_info(loop, url=self.webpage_url, download=dl)
            logger.debug('Got info')

            self.info_from_dict(**info)
            print('[INFO] Downloaded', self.webpage_url)
            if dl:
                self.filename = self.playlist.downloader.safe_ytdl.prepare_filename(info)
            else:
                self.filename = self.url

            logger.debug('Filename set to {}'.format(self.filename))
            self.success = True
            return

        except Exception as e:
            logger.debug('Download error: {}'.format(e))
            await self.playlist.bot.send_message(self.playlist.channel, 'Failed to download {0}\n{1}'.format(self.title, e))

        finally:
            self._downloading = False
            self.playlist.bot.loop.call_soon_threadsafe(self.on_ready.set)

    async def delete_file(self):
        for i in range(0, 2):
            try:
                if not os.path.exists(self.filename):
                    return

                os.remove(self.filename)
                print('[INFO] Deleted', self.filename)
                break
            except PermissionError:
                await asyncio.sleep(1)
                pass