from __future__ import annotations

import logging
import os
import openai

logger = logging.getLogger(__name__)

class LyricRefiner:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for lyric refinement")
        self.client = openai.OpenAI(api_key=self.api_key)

    def refine(self, official_lyrics: str, asr_text: str) -> str:
        """
        Refine the lyrics by merging official lyrics with ASR output.
        ASR output might contain sung parts (chorus, ad-libs, background vocals) 
        that are missing from the official lyrics.
        Official lyrics provide the correct spelling and structure.
        """
        logger.info("Refining lyrics with OpenAI...")
        
        prompt = f"""
You are a karaoke production expert. I have two versions of a song's lyrics:
1. OFFICIAL LYRICS (may be missing some sung parts like choruses, back vocals, or ad-libs).
2. ASR OUTPUT (transcribed from audio, contains exactly what was sung but might have misspellings or poor formatting).

Your task is to generate a COMPLETE "Singing Transcript" that:
- Includes EVERYTHING actually sung in the ASR output.
- Uses the spelling, punctuation, and style of the OFFICIAL LYRICS whenever they match.
- If the ASR contains parts NOT in the official lyrics (like repeated choruses or back vocals), include them clearly using the best spelling guess.
- Maintain the line structure of the official lyrics where possible, but add new lines for new sung parts.
- DO NOT add timestamps or metadata. Just the plain text lines.

OFFICIAL LYRICS:
{official_lyrics}

ASR OUTPUT:
{asr_text}

FINAL SINGING TRANSCRIPT:
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional lyric editor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            refined = response.choices[0].message.content.strip()
            # Remove markdown code blocks if any
            if refined.startswith("```"):
                refined = "\n".join(refined.splitlines()[1:-1])
            
            logger.info("Lyric refinement successful")
            return refined
        except Exception as e:
            logger.error(f"Lyric refinement failed: {e}")
            return official_lyrics # Fallback to official lyrics
