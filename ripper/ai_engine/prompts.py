"""
ripper.ai_engine.prompts
~~~~~~~~~~~~~~~~~~~~~~~~

High-precision prompt templates optimized for K2-Horizon and small language models.
Formats follow standard ChatML (<|im_start|> / <|im_end|>) conventions.
"""

from typing import Optional


CHATML_SYSTEM = "<|im_start|>system\n{content}<|im_end|>\n"
CHATML_USER = "<|im_start|>user\n{content}<|im_end|>\n"
CHATML_ASSISTANT = "<|im_start|>assistant\n{content}<|im_end|>\n"


MEDIA_EXTRACTION_SYSTEM = """You are a high-speed, precision structured data extractor for media URLs and video links.
Extract movie name, quality (480P, 720P, 1080P, 2160P), codec (X264, HEVC, REMUX), size, audio, and download/stream URL.
Output MUST be strict JSON only."""


MEDIA_EXTRACTION_USER_TEMPLATE = """Analyze this condensed webpage DOM from {base_url}.
Find all movie/series download links or streaming mirrors.

Return ONLY valid JSON matching this schema:
{{
  "movie_name": "Title of Movie or Series",
  "items": [
    {{
      "quality": "1080P",
      "codec": "HEVC",
      "size": "2.4GB",
      "audio": "Dual Audio [Hindi+English]",
      "url": "https://..."
    }}
  ]
}}

WEBPAGE DATA:
{condensed_dom}
"""


QUERY_PLANNING_SYSTEM = """You are an expert natural language query planner for video and media searches.
Parse the user's search query into exact title, year, season, episode, quality, codec, audio preferences, and search keywords.
Output MUST be strict JSON only."""


QUERY_PLANNING_USER_TEMPLATE = """Parse this user query into a structured media search plan:
"{query}"

Return ONLY valid JSON matching this schema:
{{
  "cleaned_title": "Interstellar",
  "media_type": "movie",
  "year": 2014,
  "season": null,
  "episode": null,
  "quality_target": "1080P",
  "codec_preference": "HEVC",
  "audio_preference": "Dual Audio",
  "search_keywords": ["interstellar", "2014", "1080p", "hevc"]
}}
"""


def build_chatml_prompt(system_prompt: str, user_content: str) -> str:
    """
    Constructs full prompt string with K2-Horizon ChatML markers.
    """
    return (
        CHATML_SYSTEM.format(content=system_prompt)
        + CHATML_USER.format(content=user_content)
        + "<|im_start|>assistant\n"
    )
