"""Installer package — components that bring a host up to Frappe-ready state.

Every installer component exposes a two-phase contract: ``plan()`` returns a
list of steps without touching the system, and ``apply()`` executes them.
The orchestrator in :mod:`benchbox_core.installer.runner` sequences components
and short-circuits on the first failure.

Public surface re-exported here; internal helpers live in underscored modules.
"""

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
from benchbox_core.installer.mariadb import MariaDBComponent
from benchbox_core.installer.node import NodeComponent
from benchbox_core.installer.redis import RedisComponent
from benchbox_core.installer.runner import install

__all__ = [
    "AptComponent",
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
    "install",
]
