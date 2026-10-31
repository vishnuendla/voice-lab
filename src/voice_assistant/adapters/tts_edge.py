from __future__ import annotations

import asyncio
import os
import tempfile
import uuid

import edge_tts
import pygame

from voice_assistant.config import Settings
from voice_assistant.domain.errors import AudioPlaybackError


class EdgeTextToSpeech:
    def __init__(self, settings: Settings):
        self._voice = settings.tts_voice
        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        try:
            pygame.mixer.init()
        except Exception as exc:
            raise AudioPlaybackError("Could not initialize audio playback") from exc
        self._loop = asyncio.new_event_loop()
        self._started = True

    def speak(self, text: str) -> None:
        if not self._started or self._loop is None:
            raise AudioPlaybackError("TTS is not started")
        if not text or not text.strip():
            return
        try:
            self._loop.run_until_complete(self._speak_async(text.strip()))
        except AudioPlaybackError:
            raise
        except Exception as exc:
            raise AudioPlaybackError("Speech playback failed") from exc

    async def _speak_async(self, text: str) -> None:
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix=f"tts-{uuid.uuid4().hex}-")
        os.close(fd)
        try:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(path)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
        finally:
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def shutdown(self) -> None:
        if self._loop is not None:
            self._loop.close()
            self._loop = None
        if self._started:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        self._started = False
