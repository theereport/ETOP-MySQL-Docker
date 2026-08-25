"""
Automatic discovery of ETOP PlatformModule implementations.

The discovery system scans a Python package such as ``modules`` and looks for
concrete PlatformModule subclasses inside files named ``module.py``.

Only module classes defined directly inside the discovered module file are
instantiated. Imported PlatformModule classes are ignored.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Iterable

from .module import PlatformModule


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModuleDiscoveryFailure:
    """
    Information about a package that could not be inspected.
    """

    package_name: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ModuleDiscoveryResult:
    """
    Result returned by automatic module discovery.
    """

    modules: tuple[PlatformModule, ...]
    scanned_packages: tuple[str, ...]
    skipped_packages: tuple[str, ...]
    failures: tuple[ModuleDiscoveryFailure, ...]

    @property
    def discovered_count(self) -> int:
        return len(self.modules)

    @property
    def failure_count(self) -> int:
        return len(self.failures)


def _find_platform_module_classes(
    imported_module: ModuleType,
) -> list[type[PlatformModule]]:
    """
    Find concrete PlatformModule subclasses defined in a Python module.
    """

    discovered_classes: list[type[PlatformModule]] = []

    for _, candidate in inspect.getmembers(
        imported_module,
        inspect.isclass,
    ):
        if candidate is PlatformModule:
            continue

        if not issubclass(candidate, PlatformModule):
            continue

        # Do not instantiate a class merely imported into module.py.
        if candidate.__module__ != imported_module.__name__:
            continue

        if inspect.isabstract(candidate):
            continue

        discovered_classes.append(candidate)

    return discovered_classes


def _module_sort_key(
    platform_module: PlatformModule,
) -> tuple[str, str]:
    metadata = platform_module.metadata

    return (
        metadata.name.casefold(),
        metadata.version,
    )


def discover_platform_modules(
    package_name: str = "modules",
    *,
    excluded_modules: Iterable[str] = (),
    strict: bool = False,
) -> ModuleDiscoveryResult:
    """
    Discover ETOP modules from child packages.

    Expected package structure::

        modules/
            customer_360/
                __init__.py
                module.py

    The discovery service imports ``<child_package>.module`` and instantiates
    each concrete PlatformModule subclass defined directly in that file.

    Args:
        package_name:
            Root Python package to scan.

        excluded_modules:
            Module metadata names or child package names that must not be
            loaded yet.

        strict:
            When True, the first import or construction error is raised.
            When False, the error is recorded and discovery continues.

    Returns:
        A ModuleDiscoveryResult containing modules and diagnostics.
    """

    exclusions = {
        item.casefold()
        for item in excluded_modules
    }

    root_package = importlib.import_module(package_name)

    if not hasattr(root_package, "__path__"):
        raise ValueError(
            f"Package {package_name!r} does not expose a package path."
        )

    discovered: list[PlatformModule] = []
    scanned_packages: list[str] = []
    skipped_packages: list[str] = []
    failures: list[ModuleDiscoveryFailure] = []

    discovered_names: set[str] = set()

    child_packages = sorted(
        pkgutil.iter_modules(
            root_package.__path__,
            prefix=f"{package_name}.",
        ),
        key=lambda item: item.name.casefold(),
    )

    for child in child_packages:
        child_name = child.name
        short_name = child_name.rsplit(".", 1)[-1]

        if not child.ispkg:
            continue

        if short_name.casefold() in exclusions:
            skipped_packages.append(child_name)
            continue

        platform_module_path = f"{child_name}.module"

        try:
            imported_module = importlib.import_module(
                platform_module_path
            )

        except ModuleNotFoundError as exc:
            # A package without module.py is not automatically an error.
            # A missing dependency imported by module.py is an actual failure.
            if exc.name == platform_module_path:
                skipped_packages.append(child_name)
                continue

            failure = ModuleDiscoveryFailure(
                package_name=platform_module_path,
                error_type=type(exc).__name__,
                message=str(exc),
            )

            failures.append(failure)

            logger.exception(
                "Unable to import ETOP module package %s.",
                platform_module_path,
            )

            if strict:
                raise

            continue

        except Exception as exc:
            failure = ModuleDiscoveryFailure(
                package_name=platform_module_path,
                error_type=type(exc).__name__,
                message=str(exc),
            )

            failures.append(failure)

            logger.exception(
                "Unable to import ETOP module package %s.",
                platform_module_path,
            )

            if strict:
                raise

            continue

        scanned_packages.append(platform_module_path)

        module_classes = _find_platform_module_classes(
            imported_module
        )

        if not module_classes:
            skipped_packages.append(platform_module_path)
            continue

        for module_class in module_classes:
            try:
                instance = module_class()
                metadata_name = instance.metadata.name

                if (
                    metadata_name.casefold()
                    in exclusions
                ):
                    skipped_packages.append(
                        platform_module_path
                    )
                    continue

                normalized_name = metadata_name.casefold()

                if normalized_name in discovered_names:
                    raise ValueError(
                        "Duplicate platform module name discovered: "
                        f"{metadata_name!r}"
                    )

                discovered_names.add(normalized_name)
                discovered.append(instance)

            except Exception as exc:
                failure = ModuleDiscoveryFailure(
                    package_name=(
                        f"{platform_module_path}."
                        f"{module_class.__name__}"
                    ),
                    error_type=type(exc).__name__,
                    message=str(exc),
                )

                failures.append(failure)

                logger.exception(
                    "Unable to construct ETOP module %s.%s.",
                    platform_module_path,
                    module_class.__name__,
                )

                if strict:
                    raise

    discovered.sort(
        key=_module_sort_key
    )

    return ModuleDiscoveryResult(
        modules=tuple(discovered),
        scanned_packages=tuple(scanned_packages),
        skipped_packages=tuple(skipped_packages),
        failures=tuple(failures),
    )