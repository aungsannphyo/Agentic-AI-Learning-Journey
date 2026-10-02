from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Provider-independent interface for language model clients."""

    @abstractmethod
    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a prompt to the LLM and return generated text."""
        raise NotImplementedError
