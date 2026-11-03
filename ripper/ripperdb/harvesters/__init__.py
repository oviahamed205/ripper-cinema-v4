"""
ripper.ripperdb.harvesters
~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype harvesters and federated dispatcher for ripperdb.
"""

from ripper.ripperdb.harvesters.base import BaseHarvester, HarvesterHealth, calculate_quality_score
from ripper.ripperdb.harvesters.ddl import DDLHarvester
from ripper.ripperdb.harvesters.dispatcher import HarvesterDispatcher
from ripper.ripperdb.harvesters.dooplay import DooPlayHarvester
from ripper.ripperdb.harvesters.embed import EmbedHarvester
from ripper.ripperdb.harvesters.pstream import PStreamHarvester
from ripper.ripperdb.harvesters.torrent import TorrentHarvester

__all__ = [
    "BaseHarvester",
    "HarvesterHealth",
    "calculate_quality_score",
    "PStreamHarvester",
    "DooPlayHarvester",
    "EmbedHarvester",
    "TorrentHarvester",
    "DDLHarvester",
    "HarvesterDispatcher",
]
