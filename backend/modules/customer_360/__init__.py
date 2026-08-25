"""
Customer 360 module exports.
"""

from .router import router
from .module import Module
from .repository import CustomerRepository, customer_repository
from .service import CustomerService, customer_service

__all__ = [
    "CustomerRepository",
    "CustomerService",
    "Module",
    "customer_repository",
    "customer_service",
    "router",
]