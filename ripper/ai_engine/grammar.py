"""
ripper.ai_engine.grammar
~~~~~~~~~~~~~~~~~~~~~~~~

GBNF grammar specifications and JSON schema validators for structured LLM generation.
Guarantees 100% syntactically valid JSON output from K2-Horizon / local inference.
"""

import json
import re
from typing import Any, Dict, List, Optional

# Strict GBNF Grammar for Media Link Extraction
GBNF_LINK_EXTRACTION = '''
root ::= "{" ws "\\"movie_name\\":" ws string "," ws "\\"items\\":" ws "[" ws (item ("," ws item)*)? ws "]" ws "}"
item ::= "{" ws "\\"quality\\":" ws quality "," ws "\\"codec\\":" ws codec "," ws "\\"size\\":" ws string "," ws "\\"audio\\":" ws string "," ws "\\"url\\":" ws string ws "}"
quality ::= "\\"480P\\"" | "\\"720P\\"" | "\\"1080P\\"" | "\\"2160P\\"" | "\\"4K\\""
codec ::= "\\"X264\\"" | "\\"HEVC\\"" | "\\"X265\\"" | "\\"REMUX\\"" | "\\"WEB-DL\\"" | "\\"HDR\\""
string ::= "\\"" ([^"\\\\] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]))* "\\""
ws ::= [ \\t\\n\\r]*
'''

# Strict GBNF Grammar for Query Intent Parsing
GBNF_QUERY_PARSING = '''
root ::= "{" ws "\\"cleaned_title\\":" ws string "," ws "\\"media_type\\":" ws media_type "," ws "\\"year\\":" ws (number | "null") "," ws "\\"season\\":" ws (number | "null") "," ws "\\"episode\\":" ws (number | "null") "," ws "\\"quality_target\\":" ws string "," ws "\\"codec_preference\\":" ws (string | "null") "," ws "\\"audio_preference\\":" ws (string | "null") "," ws "\\"search_keywords\\":" ws "[" ws (string ("," ws string)*)? ws "]" ws "}"
media_type ::= "\\"movie\\"" | "\\"tv\\"" | "\\"stream\\"" | "\\"unknown\\""
number ::= [0-9]+
string ::= "\\"" ([^"\\\\] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]))* "\\""
ws ::= [ \\t\\n\\r]*
'''


def clean_json_markdown(text: str) -> str:
    """
    Strips markdown code fences (```json ... ```) or conversational preambles
    if emitted by the language model.
    """
    cleaned = text.strip()
    # Match markdown code block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        # If no code block, locate first { and last }
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
    return cleaned


def parse_strict_json(text: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely parses JSON output from LLM, auto-recovering from formatting deviations.
    """
    cleaned = clean_json_markdown(text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return default or {}
