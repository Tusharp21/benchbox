"""Installer components: plan() then apply(), sequenced by runner.install()."""

from __future__ import annotations

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer._types import (
    Component,
    ComponentPlan,
    ComponentResult,
    InstallResult,
    Step,
    StepResult,
)
from benchbox_core.installer.apt import AptComponent
from benchbox_core.installer.bench_cli import BenchCliComponent
from benchbox_core.installer.mariadb import MariaDBComponent
from benchbox_core.installer.node import NodeComponent
from benchbox_core.installer.redis import RedisComponent
from benchbox_core.installer.runner import install
from benchbox_core.installer.wkhtmltopdf import WkhtmltopdfComponent

__all__ = [
    "AptComponent",
    "BenchCliComponent",
    "CommandResult",
    "CommandRunner",
    "Component",
    "ComponentPlan",
    "ComponentResult",
    "InstallResult",
    "MariaDBComponent",
    "NodeComponent",
    "RedisComponent",
    "Step",
    "StepResult",
    "WkhtmltopdfComponent",
    "install",
]
