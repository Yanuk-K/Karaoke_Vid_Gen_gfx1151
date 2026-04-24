from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    id: str | None = None
    text: str
    ruby: str | None = None
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    source: Literal["model", "user_edited"] = "model"
    locked: bool = False


class LineTiming(BaseModel):
    id: str | None = None
    text: str
    display_start: float = Field(ge=0)
    sing_start: float = Field(ge=0)
    end: float = Field(ge=0)
    source: Literal["model", "user_edited"] = "model"
    locked: bool = False
    words: list[WordTiming] = []


class MelodyExclusionRange(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class TimingPatchRequest(BaseModel):
    version: int = 1
    countdown_offset: float = 2.0
    next_line_lead_time: float = 0.9
    title: str | None = None
    artist: str | None = None
    enable_word_timing: bool = True
    auto_mute_melody_gaps: bool = True
    melody_gain_db: float = -14.0
    enable_melody_visualizer: bool = False
    lines: list[LineTiming]
    melody_exclusion_ranges: list[MelodyExclusionRange] = []
