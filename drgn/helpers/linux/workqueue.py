# Copyright (c) 2022, Oracle and/or its affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Workqueue
--------------

The ``drgn.helpers.linux.workqueue`` module provides helpers for working with the
Linux workqueues.
"""

from typing import Iterator, Optional, Union

from drgn import Object, Program, cast
from drgn.helpers.common.format import escape_ascii_string
from drgn.helpers.linux.idr import idr_for_each
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.percpu import per_cpu

__all__ = (
    "for_each_workqueue",
    "for_each_pool",
    "for_each_pending_work",
    "for_each_worker",
    "for_each_pool_worker",
    "for_each_pwq",
    "for_each_cpu_worker_pool",
    "for_each_pending_work_on_cpu",
    "for_each_pending_work_in_pool",
    "find_workqueue",
    "print_workqueues",
)


def for_each_workqueue(prog: Program) -> Iterator[Object]:
    """
    Iterate over all workqueues in the system.

    :return: Iterator of ``struct workqueue_struct *`` objects.
    """
    return list_for_each_entry(
        "struct workqueue_struct", prog["workqueues"].address_of_(), "list"
    )


def for_each_pool(prog: Program) -> Iterator[Object]:
    """
    Iterate over all worker_pools in the system.

    :return: Iterator of ``struct worker_pool *`` objects.
    """
    for nr, entry in idr_for_each(prog["worker_pool_idr"].address_of_()):
        yield cast("struct worker_pool *", entry)


def for_each_pending_work(prog: Program) -> Iterator[Object]:
    """
    Iterate over all pending work items (work_struct)

    :return: Iterator of ``struct work_struct *`` objects.
    """
    for nr, entry in idr_for_each(prog["worker_pool_idr"].address_of_()):
        wp = cast("struct worker_pool *", entry)
        for work in list_for_each_entry(
            "struct work_struct", wp.worklist.address_of_(), "entry"
        ):
            yield work


def for_each_pool_worker(pool: Object) -> Iterator[Object]:
    """
    Iterate over all workers in a worker_pool

    :return: Iterator of ``struct worker *`` objects.
    """
    for worker in list_for_each_entry(
        "struct worker", pool.workers.address_of_(), "node"
    ):
        yield worker


def for_each_worker(prog: Program) -> Iterator[Object]:
    """
    Iterate over all workers in a system

    :return: Iterator of ``struct worker *`` objects.
    """
    for nr, entry in idr_for_each(prog["worker_pool_idr"].address_of_()):
        pool = Object(prog, "struct worker_pool", address=entry.value_())
        for worker in for_each_pool_worker(pool):
            yield worker


def for_each_pwq(workqueue: Object) -> Iterator[Object]:
    """
    Iterate over all pool_workqueues of a specified workqueue

    :return: Iterator of ``struct pool_workqueue *`` objects.
    """
    return list_for_each_entry(
        "struct pool_workqueue", workqueue.pwqs.address_of_(), "pwqs_node"
    )


def for_each_cpu_worker_pool(prog: Program, cpu: int) -> Iterator[Object]:
    """
    Iterate over all worker_pool(s) of a CPU

    :return: Iterator of ``struct worker_pool *`` objects.
    """
    worker_pool_list = per_cpu(prog["cpu_worker_pools"], cpu)
    for worker_pool in worker_pool_list:
        yield worker_pool.address_of_()


def for_each_pending_work_in_pool(worker_pool: Object) -> Iterator[Object]:
    """
    Iterate over all works pending in a worker_pool

    :return: Iterator of ``struct work_struct *`` objects.
    """
    return list_for_each_entry(
        "struct work_struct", worker_pool.worklist.address_of_(), "entry"
    )


def for_each_pending_work_on_cpu(prog: Program, cpu: int) -> Iterator[Object]:
    """
    Iterate over all works pending in a CPU's worker_pools

    :return: Iterator of ``struct work_struct *`` objects.
    """
    for worker_pool in for_each_cpu_worker_pool(prog, cpu):
        for work in for_each_pending_work_in_pool(worker_pool):
            yield work


def find_workqueue(prog: Program, name: Union[str, bytes]) -> Optional[Object]:
    """
    Find workqueue with the given name

    :param name: workqueue name.
    :return: ``struct workqueue *``
    """
    if isinstance(name, str):
        name = name.encode()
    for workqueue in for_each_workqueue(prog):
        if workqueue.name.string_() == name:
            return workqueue
    return None


def print_workqueues(prog: Program) -> None:
    """Print the name and ``struct workqueue_struct *`` value of all workqueues."""
    for workqueue in for_each_workqueue(prog):
        name = escape_ascii_string(workqueue.name.string_(), escape_backslash=True)
        print(f"{name} ({workqueue.type_.type_name()})0x{workqueue.value_():x}")
