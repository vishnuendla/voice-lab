from __future__ import annotations

import os
import tempfile

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.io.wavfile import write

from voice_assistant.config import Settings
from voice_assistant.domain.errors import TranscriptionError
from voice_assistant.domain.models import Transcript

_INITIAL_PROMPT = """
This conversation contains technical terms such as:

NEET
JEE
IPL
NVIDIA
OpenRouter
Groq
Tavily
FastAPI
Whisper
ChatGPT
"""


class WhisperSpeechToText:
    def __init__(self, settings: Settings, model: WhisperModel | None = None):
        self._settings = settings
        self._model = model or WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )

    def listen(self) -> Transcript:
        samplerate = 44100
        duration = self._settings.record_duration_seconds
        try:
            recording = sd.rec(
                int(duration * samplerate),
                samplerate=samplerate,
                channels=1,
                dtype=np.int16,
            )
            sd.wait()
        except Exception as exc:
            raise TranscriptionError("Microphone recording failed") from exc

        audio_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                write(handle.name, samplerate, recording)
                audio_file = handle.name

            segments, _info = self._model.transcribe(
                audio_file,
                language=self._settings.language,
                beam_size=5,
                initial_prompt=_INITIAL_PROMPT,
            )
            segments = list(segments)
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError("Transcription failed") from exc
        finally:
            if audio_file and os.path.exists(audio_file):
                os.remove(audio_file)

        if not segments:
            return Transcript(text="", confidence=-999.0)

        text = " ".join(segment.text.strip() for segment in segments).strip()
        confidence = sum(segment.avg_logprob for segment in segments) / len(segments)
        return Transcript(text=text, confidence=confidence)
