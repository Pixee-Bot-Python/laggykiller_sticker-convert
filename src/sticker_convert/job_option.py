#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import ceil
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any, Optional, Union


def to_int(i: Union[float, str, None]) -> Optional[int]:
    return int(i) if i is not None else None


@dataclass
class BaseOption:
    def merge(self, config: "BaseOption"):
        for k, v in vars(config).items():
            if v is not None:
                setattr(self, k, v)

    def __repr__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict[str, str]:
        return dict()


@dataclass
class InputOption(BaseOption):
    option: str = "local"
    url: str = ""
    dir: Path = Path()

    def to_dict(self) -> dict[Any, Any]:
        return {"option": self.option, "url": self.url, "dir": self.dir.as_posix()}


@dataclass
class CompOption(BaseOption):
    preset: str = "auto"
    size_max_img: Optional[int] = None
    size_max_vid: Optional[int] = None

    format_img: list[str] = field(default_factory=lambda: [])
    format_vid: list[str] = field(default_factory=lambda: [])

    fps_min: Optional[int] = None
    fps_max: Optional[int] = None
    fps_power: float = -0.5

    res_w_min: Optional[int] = None
    res_w_max: Optional[int] = None
    res_h_min: Optional[int] = None
    res_h_max: Optional[int] = None
    res_power: float = 3.0

    quality_min: Optional[int] = None
    quality_max: Optional[int] = None
    quality_power: float = 5.0

    color_min: Optional[int] = None
    color_max: Optional[int] = None
    color_power: float = 3.0

    duration_min: Optional[int] = None
    duration_max: Optional[int] = None

    steps: int = 1
    fake_vid: Optional[bool] = None
    quantize_method: Optional[str] = None
    scale_filter: Optional[str] = None
    cache_dir: Optional[str] = None
    default_emoji: str = "😀"
    no_compress: Optional[bool] = None
    processes: int = ceil(cpu_count() / 2)
    animated: Optional[bool] = None
    square: Optional[bool] = None

    def to_dict(self) -> dict[Any, Any]:
        return {
            "preset": self.preset,
            "size_max": {"img": self.size_max_img, "vid": self.size_max_vid},
            "format": {"img": self.format_img, "vid": self.format_vid},
            "fps": {"min": self.fps_min, "max": self.fps_max, "power": self.fps_power},
            "res": {
                "w": {"min": self.res_w_min, "max": self.res_w_max},
                "h": {"min": self.res_h_min, "max": self.res_h_max},
                "power": self.res_power,
            },
            "quality": {
                "min": self.quality_min,
                "max": self.quality_max,
                "power": self.quality_power,
            },
            "color": {
                "min": self.color_min,
                "max": self.color_max,
                "power": self.color_power,
            },
            "duration": {"min": self.duration_min, "max": self.duration_max},
            "steps": self.steps,
            "fake_vid": self.fake_vid,
            "scale_filter": self.scale_filter,
            "cache_dir": self.cache_dir,
            "default_emoji": self.default_emoji,
            "no_compress": self.no_compress,
            "processes": self.processes,
            "animated": self.animated,
            "square": self.square,
        }

    def get_size_max(self) -> list[Optional[int]]:
        return [self.size_max_img, self.size_max_vid]

    def set_size_max(self, value: Optional[int]):
        self.size_max_img, self.size_max_vid = to_int(value), to_int(value)

    def get_format(self) -> list[list[str]]:
        return [self.format_img, self.format_vid]

    def set_format(self, value: list[str]):
        self.format_img, self.format_vid = value, value

    def get_fps(self) -> list[Optional[int]]:
        return [self.fps_min, self.fps_max]

    def set_fps(self, value: Optional[int]):
        self.fps_min, self.fps_max = to_int(value), to_int(value)

    def get_res(self) -> list[list[Optional[int]]]:
        return [self.get_res_w(), self.get_res_h()]

    def set_res(self, value: Optional[int]):
        self.res_w_min = to_int(value)
        self.res_w_max = to_int(value)
        self.res_h_min = to_int(value)
        self.res_h_max = to_int(value)

    def get_res_max(self) -> list[Optional[int]]:
        return [self.res_w_max, self.res_h_max]

    def set_res_max(self, value: Optional[int]):
        self.res_w_max = to_int(value)
        self.res_h_max = to_int(value)

    def get_res_min(self) -> list[Optional[int]]:
        return [self.res_w_min, self.res_h_min]

    def set_res_min(self, value: Optional[int]):
        self.res_w_min = to_int(value)
        self.res_h_min = to_int(value)

    def get_res_w(self) -> list[Optional[int]]:
        return [self.res_w_min, self.res_w_max]

    def set_res_w(self, value: Optional[int]):
        self.res_w_min, self.res_w_max = to_int(value), to_int(value)

    def get_res_h(self) -> list[Optional[int]]:
        return [self.res_h_min, self.res_h_max]

    def set_res_h(self, value: Optional[int]):
        self.res_h_min, self.res_h_max = to_int(value), to_int(value)

    def get_quality(self) -> list[Optional[int]]:
        return [self.quality_min, self.quality_max]

    def set_quality(self, value: Optional[int]):
        self.quality_min, self.quality_max = to_int(value), to_int(value)

    def get_color(self) -> list[Optional[int]]:
        return [self.color_min, self.color_max]

    def set_color(self, value: Optional[int]):
        self.color_min, self.color_max = to_int(value), to_int(value)

    def get_duration(self) -> list[Optional[int]]:
        return [self.duration_min, self.duration_max]

    def set_duration(self, value: Optional[int]):
        self.duration_min, self.duration_max = to_int(value), to_int(value)


@dataclass
class OutputOption(BaseOption):
    option: str = "local"
    dir: Path = Path()
    title: str = ""
    author: str = ""

    def to_dict(self) -> dict[Any, Any]:
        return {
            "option": self.option,
            "dir": self.dir.as_posix(),
            "title": self.title,
            "author": self.author,
        }


@dataclass
class CredOption(BaseOption):
    signal_uuid: str = ""
    signal_password: str = ""
    telegram_token: str = ""
    telegram_userid: str = ""
    kakao_auth_token: str = ""
    kakao_username: str = ""
    kakao_password: str = ""
    kakao_country_code: str = ""
    kakao_phone_number: str = ""
    line_cookies: str = ""

    def to_dict(self) -> dict[Any, Any]:
        return {
            "signal": {"uuid": self.signal_uuid, "password": self.signal_password},
            "telegram": {"token": self.telegram_token, "userid": self.telegram_userid},
            "kakao": {
                "auth_token": self.kakao_auth_token,
                "username": self.kakao_username,
                "password": self.kakao_password,
                "country_code": self.kakao_country_code,
                "phone_number": self.kakao_phone_number,
            },
            "line": {"cookies": self.line_cookies},
        }
