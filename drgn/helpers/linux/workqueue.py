# Copyright (c) 2022, Oracle and/or its affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Workqueue
--------------

The ``drgn.helpers.linux.workqueue`` module provides helpers for working with the
Linux workqueues.
"""

from typing import Iterator, Optional, Union

from drgn import NULL, Object, Program, cast
from drgn.helpers.common.format import escape_ascii_string
from drgn.helpers.linux.idr import idr_find, idr_for_each
from drgn.helpers.linux.list import (
    hlist_for_each_entry,
    list_empty,
    list_for_each_entry,
)
from drgn.helpers.linux.percpu import per_cpu
from drgn.helpers.linux.pid import find_task

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
    "for_each_pending_work_of_pwq",
    "find_workqueue",
    "get_work_pwq",
    "get_work_pool",
    "print_workqueue_names",
    "show_pwq",
    "show_all_workqueues",
    "show_one_workqueue",
    "show_one_worker_pool",
    "is_task_a_worker",
    "find_worker_executing_work",
)


_PF_WQ_WORKER = 0x00000020


def _print_work(work: Object) -> None:
    prog = work.prog_
    print(
        f"        ({work.type_.type_name()})0x{work.value_():x}: func: {prog.symbol(work.func.value_()).name}"
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


def for_each_pending_work_of_pwq(pwq: Object) -> Iterator[Object]:
    """
    Iterate over all pending works of a pool_workqueue

    :return: Iterator of ``struct work_struct *`` objects.
    """
    pool = pwq.pool
    for work in for_each_pending_work_in_pool(pool):
        if get_work_pwq(work).value_() == pwq.value_():
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


def print_workqueue_names(prog: Program) -> None:
    """Print the name and ``struct workqueue_struct *`` value of all workqueues."""
    for workqueue in for_each_workqueue(prog):
        name = escape_ascii_string(workqueue.name.string_(), escape_backslash=True)
        print(f"{name} ({workqueue.type_.type_name()})0x{workqueue.value_():x}")


def get_work_pwq(work: Object) -> Object:
    """
    Get pool_workqueue associated with a work

    :param work: ``struct work_struct *``

    :return: ``struct pool_workqueue *`` of associated pwq, NULL otherwise

    """

    prog = work.prog_
    data = cast("unsigned long", work.data.counter.read_())
    if data & prog["WORK_STRUCT_PWQ"].value_():
        return cast(
            "struct pool_workqueue *", data & prog["WORK_STRUCT_WQ_DATA_MASK"].value_()
        )
    else:
        return NULL(work.prog_, "struct pool_workqueue *")


def get_work_pool(work: Object) -> Object:
    """
    Get worker_pool associated with a work

    :param work: ``struct work_struct *``

    :return: ``struct worker_pool *`` of associated pool, NULL otherwise
             residing in a worker_pool at the moment

    """

    prog = work.prog_
    data = cast("unsigned long", work.data.counter.read_())

    if data & prog["WORK_STRUCT_PWQ"].value_():
        pwq = data & prog["WORK_STRUCT_WQ_DATA_MASK"].value_()
        pool = Object(prog, "struct pool_workqueue", address=pwq).pool
    else:
        pool_id = data >> prog["WORK_OFFQ_POOL_SHIFT"].value_()

        if pool_id == prog["WORK_OFFQ_POOL_NONE"].value_():
            return NULL(work.prog_, "struct worker_pool *")

        pool = idr_find(prog["worker_pool_idr"].address_of_(), pool_id)

        pool = cast("struct worker_pool *", pool)

    return pool


def show_pwq_in_flight(pwq: Object) -> None:
    """
    Show in_flight work items of a pwq

    :param pwq: ``struct pwq *``.
    """
    pool = pwq.pool
    has_in_flight = False
    prog = pwq.prog_

    for bkt in pool.busy_hash:
        for worker in hlist_for_each_entry("struct worker", bkt, "hentry"):
            if worker.current_pwq.value_() == pwq.value_():
                has_in_flight = True
                break

        if has_in_flight:
            break

    if not has_in_flight:
        print("  There are no in-flight work items for this pwq.")
    else:
        print("  in-flight:")
        for bkt in pool.busy_hash:
            for worker in hlist_for_each_entry("struct worker", bkt, "hentry"):
                if worker.current_pwq.value_() == pwq.value_():
                    pid = worker.task.pid.value_()
                    rescuer = "(RESCUER)" if worker.rescue_wq else ""
                    current_work = worker.current_work.value_()
                    current_func = prog.symbol(worker.current_func.value_()).name
                    print(
                        f"    worker pid: {pid} {rescuer} current_work: {hex(current_work)}  current_func: {current_func}"
                    )
                    if list_empty(worker.scheduled.address_of_()):
                        print("    There are no scheduled works for this worker")
                    else:
                        print("    Scheduled work(s): ")
                        for work in list_for_each_entry(
                            "struct work_struct",
                            worker.scheduled.address_of_(),
                            "entry",
                        ):
                            _print_work(work)


def show_pwq_pending(pwq: Object) -> None:
    """
    Show pending work items of a pwq

    :param pwq: ``struct pwq *``.
    """
    prog = pwq.prog_
    pool = Object(
        pwq.prog_, "struct worker_pool", address=pwq.pool.value_()
    ).address_of_()
    has_pending = False

    for work in for_each_pending_work_in_pool(pool):
        if get_work_pwq(work).value_() == pwq.value_():
            has_pending = True
            break

    if not has_pending:
        print("  There are no pending work items for this pwq.")
    else:
        print("  pending:")
        pool = Object(prog, "struct worker_pool", address=pwq.pool.value_())
        for work in for_each_pending_work_of_pwq(pwq):
            _print_work(work)


def show_pwq_inactive(pwq: Object) -> None:
    """
    Show pending work items of a pwq

    :param pwq: ``struct pwq *``.
    """

    # Since Linux kernel commit f97a4a1a3f87 ("workqueue: Rename "delayed"
    # (delayed by active management) to "inactive") (in v5.15), the list
    # containing work items, delayed by workqueue active management (i.e
    # the ones that are not of type delayed_work), has been renamed from
    # "delayed_works" to "inactive_works".
    inactive_works_attr = (
        "inactive_works" if hasattr(pwq, "inactive_works") else "delayed_works"
    )
    inactive_works = getattr(pwq, inactive_works_attr).address_of_()

    if list_empty(inactive_works):
        print("  There are no inactive works for this pwq")
    else:
        print("  inactive: ")
        for work in list_for_each_entry("struct work_struct", inactive_works, "entry"):
            _print_work(work)


def show_pwq(pwq: Object) -> None:
    """
    Dump a pool_workqueue

    :param pwq: ``struct pwq *``.
    """
    if list_empty(pwq.pwqs_node.address_of_()):
        mayday = False
    else:
        mayday = True
    print(f"pwq: ({pwq.type_.type_name()})0x{pwq.value_():x}")
    print("pool id:", pwq.pool.id.value_())
    print("active/max_active ", pwq.nr_active.value_(), "/", pwq.max_active.value_())
    print(f"refcnt: {pwq.refcnt.value_()} Mayday: {mayday}")

    show_pwq_in_flight(pwq)
    show_pwq_pending(pwq)
    show_pwq_inactive(pwq)


def show_one_workqueue(workqueue: Object) -> None:
    """
    Dump a workqueue

    :param workqueue: ``struct workqueue_struct *``.
    """

    idle = True
    name = escape_ascii_string(workqueue.name.string_(), escape_backslash=True)
    print(f"{name} ({workqueue.type_.type_name()})0x{workqueue.value_():x}")

    for pwq in for_each_pwq(workqueue):
        inactive_works_attr = (
            "inactive_works" if hasattr(pwq, "inactive_works") else "delayed_works"
        )
        inactive_works = getattr(pwq, inactive_works_attr).address_of_()
        if pwq.nr_active or not list_empty(inactive_works):
            idle = False
            break

    if idle:
        print("  workqueue is idle")
    else:
        for pwq in for_each_pwq(workqueue):
            inactive_works_attr = (
                "inactive_works" if hasattr(pwq, "inactive_works") else "delayed_works"
            )
            inactive_works = getattr(pwq, inactive_works_attr).address_of_()
            if pwq.nr_active or not list_empty(inactive_works):
                show_pwq(pwq)


def show_one_worker_pool(worker_pool: Object) -> None:
    """
    Dump a worker_pool

    :param worker_pool: ``struct worker_pool *``.
    """

    print(
        f"pool: {worker_pool.id.value_()} number of workers: {worker_pool.nr_workers.value_()}"
    )

    if worker_pool.nr_workers.value_() == worker_pool.nr_idle.value_():
        print("  All workers idle.")
        return

    if worker_pool.manager:
        print(f"manager pid: {worker_pool.manager.task.pid.value_()}")

    idle_workers = [
        worker.task.pid.value_()
        for worker in list_for_each_entry(
            "struct worker", worker_pool.idle_list.address_of_(), "entry"
        )
    ]
    if idle_workers:
        print("  idle worker pids: ", idle_workers)

    print("\n")


def show_all_workqueues(prog: Program) -> None:
    """Dump state of all workqueues and worker_pools"""

    for workqueue in for_each_workqueue(prog):
        show_one_workqueue(workqueue)

    print("\n")

    for pool in for_each_pool(prog):
        show_one_worker_pool(pool)


def is_task_a_worker(prog: Program, pid: int) -> bool:
    """
    Check if specified task is a worker thread.

    :param pid: pid of task

    :return: ``True`` if task is a worker, ``False`` otherwise
    """

    task = find_task(prog, pid)

    ret = True if task.flags.value_() & _PF_WQ_WORKER else False

    return ret


def find_worker_executing_work(work: Object) -> Object:
    """
    Find the worker that is current executing the specified work

    :param work: ``struct work_struct *``.

    :return worker: ``struct worker *``.
    """

    prog = work.prog_
    pool = get_work_pool(work)

    if not pool:
        return pool

    for bkt in pool.busy_hash:
        for worker in hlist_for_each_entry("struct worker", bkt, "hentry"):
            if (
                worker.current_work == work.address_of_()
                and worker.current_func == work.func
            ):
                return worker

    return NULL(prog, "struct worker *")
