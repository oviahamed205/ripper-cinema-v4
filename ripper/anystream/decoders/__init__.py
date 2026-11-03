"""
Registers all video host decoders into ANYSTREAM_REGISTRY.
"""
from typing import List
from ..base_decoder import BaseHostDecoder
from .doodstream import DoodStreamDecoder
from .streamtape import StreamTapeDecoder
from .filelions import FileLionsDecoder
from .mixdrop import MixDropDecoder
from .voe import VoeDecoder
from .html5_generic import HTML5GenericDecoder


class AnyStreamRegistry:
    def __init__(self) -> None:
        self.decoders: List[BaseHostDecoder] = [
            DoodStreamDecoder(),
            StreamTapeDecoder(),
            FileLionsDecoder(),
            MixDropDecoder(),
            VoeDecoder(),
            HTML5GenericDecoder(),
        ]
        self.decoders.sort(key=lambda d: d.priority)

    def get_decoder(self, url: str, html: str = "") -> BaseHostDecoder:
        for d in self.decoders:
            if d.can_decode(url, html):
                return d
        return self.decoders[-1]  # HTML5Generic fallback


ANYSTREAM_REGISTRY = AnyStreamRegistry()