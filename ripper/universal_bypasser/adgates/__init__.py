"""
AdGate Solvers Package.
Exports all specific ad-gate solver implementations, social unlockers,
cloud drive gateways, and the FastForward declarative rules engine.
"""

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.adgates.adfly import AdFlySolver
from ripper.universal_bypasser.adgates.bstlar import BstlarSolver
from ripper.universal_bypasser.adgates.cloud_drive_gate import CloudDriveGateSolver
from ripper.universal_bypasser.adgates.droplink import DroplinkSolver
from ripper.universal_bypasser.adgates.fastforward_rules import FastForwardRules
from ripper.universal_bypasser.adgates.generic_fly import GenericFlySolver
from ripper.universal_bypasser.adgates.gplinks import GPLinksSolver
from ripper.universal_bypasser.adgates.linkvertise import LinkvertiseSolver
from ripper.universal_bypasser.adgates.ouo import OuoSolver
from ripper.universal_bypasser.adgates.paster_so import PasterSoSolver
from ripper.universal_bypasser.adgates.psa_wf import PSAWfSolver
from ripper.universal_bypasser.adgates.rocklinks import RocklinksSolver
from ripper.universal_bypasser.adgates.shareus import ShareusSolver
from ripper.universal_bypasser.adgates.shrinkearn import ShrinkEarnSolver
from ripper.universal_bypasser.adgates.sub2unlock import Sub2UnlockSolver
from ripper.universal_bypasser.adgates.try2link import Try2LinkSolver

__all__ = [
    "BaseAdGateSolver",
    "GPLinksSolver",
    "DroplinkSolver",
    "RocklinksSolver",
    "OuoSolver",
    "GenericFlySolver",
    "FastForwardRules",
    "Sub2UnlockSolver",
    "ShareusSolver",
    "ShrinkEarnSolver",
    "CloudDriveGateSolver",
    "LinkvertiseSolver",
    "AdFlySolver",
    "PSAWfSolver",
    "Try2LinkSolver",
    "PasterSoSolver",
    "BstlarSolver",
]
