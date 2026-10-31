class VoiceAssistantError(Exception):
    """Base error for the voice assistant."""


class ConfigurationError(VoiceAssistantError):
    """Invalid or missing configuration."""


class TranscriptionError(VoiceAssistantError):
    """Speech-to-text failed."""


class LLMError(VoiceAssistantError):
    """LLM request failed or returned an invalid payload."""


class ToolExecutionError(VoiceAssistantError):
    """Tool arguments were invalid or execution failed."""


class AudioPlaybackError(VoiceAssistantError):
    """Text-to-speech synthesis or playback failed."""
