#!/usr/bin/env drgn
# Copyright (c) 2024, Oracle and/or its affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

""" Script to dump lock information"""

import argparse

from drgn import Object
from drgn.helpers.linux.list import list_empty
from drgn.helpers.linux.locks import (
    _RWSEM_READER_MASK,
    _RWSEM_READER_SHIFT,
    get_rwsem_owner,
    get_rwsem_waiter_type,
    is_rwsem_reader_owned,
    is_rwsem_writer_owned,
    mutex_for_each_waiter_task,
    mutex_is_locked,
    mutex_owner,
    rwsem_for_each_waiter,
    rwsem_for_each_waiter_task,
    rwsem_is_locked,
    semaphore_for_each_waiter_task,
)
from drgn.helpers.linux.sched import task_state_to_char


###############################################
# mutex
###############################################
def dump_mutex_waiters_call_stack(mutex: Object) -> None:
    """
    Dump call stacks for all tasks blocked on a mutex.

    :param lock: ``struct mutex *``
    """
    prog = mutex.prog_
    print(f"Dumping call stack for waiter of mutex: {mutex.value_():x}")
    for task in mutex_for_each_waiter_task(mutex):
        trace = prog.stack_trace(task.pid.value_())
        print(f"\ncall stack for pid: {task.pid.value_()}")
        print(trace)
        print("\n")


def dump_mutex_owner_call_stack(mutex: Object) -> None:
    """
    Dump call stack of mutex owner.

    :param lock: ``struct mutex *``
    """
    prog = mutex.prog_
    if mutex_is_locked(mutex):
        owner = mutex_owner(mutex)
        print(f"Dumping call stack for owner of mutex: {mutex.value_():x}")
        trace = prog.stack_trace(owner.pid.value_())
        print(f"\ncall stack for pid: {owner.pid.value_()}")
        print(trace)
        print("\n")


def get_mutex_waiters_info(mutex: Object) -> None:
    """
    Get information about waiter(s) of a given mutex.
    This consists of ``struct task_struct *``, pid(s)
    and state of waiter(s)

    :param mutex: ``struct mutex *``
    """
    if list_empty(mutex.wait_list.address_of_()):
        print(f"  mutex: {mutex.value_():x} has no waiters.")
        return

    print(f"  The waiters of mutex: {mutex.value_():x} are as follows: ")
    for task in mutex_for_each_waiter_task(mutex):
        print(
            f"    ({task.type_.type_name()})0x{task.value_():x} pid: {task.pid.value_()} state: {task_state_to_char(task)}"
        )
    print("\n")


def get_mutex_info(mutex: Object) -> None:
    """
    Get information about given mutex.
    This consists of ``struct task_struct *``, pid(s) and state
    of owner and waiter(s) (if any).

    :param mutex: ``struct mutex *``
    """
    if mutex_is_locked(mutex):
        owner = mutex_owner(mutex)
        print(
            f"  mutex: {mutex.value_():x} is owned by ({owner.type_.type_name()})0x{owner.value_():x} pid: {owner.pid.value_()} state: {task_state_to_char(owner)}"
        )
        get_mutex_waiters_info(mutex)
    else:
        print(f"  mutex: {mutex.value_():x} is not locked.")


###############################################
# semaphore
###############################################
def get_semaphore_waiters_info(semaphore: Object) -> None:
    """
    Get information about waiter(s) of a given semaphore.
    This consists of ``struct task_struct *``, pid(s)
    and state of waiter(s)

    :param semaphore: ``struct semaphore *``
    """
    if list_empty(semaphore.wait_list.address_of_()):
        print(f"  semaphore: {semaphore.value_():x} has no waiters.")
        return

    print(f"  The waiters of semaphore: {semaphore.value_():x} are as follows: ")
    for task in semaphore_for_each_waiter_task(semaphore):
        print(
            f"    ({task.type_.type_name()})0x{task.value_():x} pid: {task.pid.value_()} state: {task_state_to_char(task)}"
        )
    print("\n")


def dump_semaphore_waiters_call_stack(semaphore: Object) -> None:
    """
    Dump call stacks for all tasks blocked on a semaphore.

    :param lock: ``struct semaphore *``
    """
    prog = semaphore.prog_
    print(f"Dumping call stack for waiter(s) of semaphore: {semaphore.value_():x}")
    for task in semaphore_for_each_waiter_task(semaphore):
        trace = prog.stack_trace(task.pid.value_())
        print(f"\ncall stack for pid: {task.pid.value_()}")
        print(trace)
        print("\n")


###############################################
# rwsem
###############################################
def get_rwsem_info(rwsem: Object) -> None:
    """
    Get information about given rwsem.
    This consists of ``struct task_struct *``, pid(s), type
    and state of owner and waiter(s) (if any).

    :param rwsem: ``struct rw_semaphore *``
    """

    # This helper supports LTS versions since v4.14. It may work with
    # other versions too but has not been tested with other versions.
    # Now from v4.14 to v5.2 ->owner is of type task_struct * and ->count
    # is adjusted/interpreted according different BIAS(es) like
    # ACTIVE_BIAS, WRITE_BIAS etc.
    # Linux kernel commit 94a9717b3c40 ('locking/rwsem: Make rwsem->owner
    # an atomic_long_t') (since v5.3.1) changed ->owner type and Linux kernel
    # commit 64489e78004c ('locking/rwsem: Implement a new locking scheme')
    # (also since v5.3.1) removed usage of different BIAS(es) and re-defined
    # usage and interpretation of ->count bits.
    # So although type change of ->owner and re-definition of ->count bits
    # happened in 2 different commits, both of these changes are available
    # since v5.3.1.
    # So we can use ->owner type to distinguish between new and old usage
    # of rwsem ->count and ->owner bits.
    if not rwsem_is_locked(rwsem):
        print(f"  rwsem: {rwsem.value_():x} is free.")
        return

    owner_is_writer = is_rwsem_writer_owned(rwsem)
    owner_is_reader = is_rwsem_reader_owned(rwsem)

    if owner_is_writer:
        owner_task = get_rwsem_owner(rwsem)
        if not owner_task:
            print(f"  rwsem: {rwsem.value_():x} is owned by anonymous writer.")
        else:
            print(
                f"  rwsem: {rwsem.value_():x} owned by writer ({owner_task.type_.type_name()})0x{owner_task.value_():x}  (pid){owner_task.pid.value_()}  (state){task_state_to_char(owner_task)} "
            )
    elif owner_is_reader:
        if rwsem.owner.type_.type_name() == "atomic_long_t":
            num_readers = (
                rwsem.count.counter.value_() & _RWSEM_READER_MASK
            ) >> _RWSEM_READER_SHIFT
            print(f"  rwsem: {rwsem.value_():x} is owned by {num_readers} reader(s).")
        else:
            print(f"  rwsem: {rwsem.value_():x} is owned by one or more readers.")
    else:
        print(f"  Can't determine type of owner for rwsem: {rwsem.value_():x}.")

    if list_empty(rwsem.wait_list.address_of_()):
        print(f"  There are no waiters for rwsem: {rwsem.value_():x}.")
    else:
        get_rwsem_waiters_info(rwsem)


def dump_rwsem_waiters_call_stack(rwsem: Object) -> None:
    """
    Dump call stack of all task(s) blocked on a given rwsem

    :param rwsem: ``struct rw_semaphore *``
    """
    if list_empty(rwsem.wait_list.address_of_()):
        print(f"  rwsem: {rwsem.value_():x} has no waiters.")
        return

    prog = rwsem.prog_
    print(f"Dumping call stack for waiter of rwsem: {rwsem.value_():x}")
    for task in rwsem_for_each_waiter_task(rwsem):
        trace = prog.stack_trace(task.pid.value_())
        print(f"\ncall stack for pid: {task.pid.value_()}")
        print(trace)
        print("\n")


def dump_rwsem_owner_call_stack(rwsem: Object) -> None:
    """
    Dump call stack of rwsem's owner (if owner could be found.")

    :param rwsem: ``struct rw_semaphore *``
    """

    prog = rwsem.prog_
    owner = get_rwsem_owner(rwsem)
    if owner:
        print(f"Dumping call stack for owner of rwsem: {rwsem.value_():x}")
        trace = prog.stack_trace(owner.pid.value_())
        print(f"\ncall stack for pid: {owner.pid.value_()}")
        print(trace)
        print("\n")
    else:
        print(
            f"rwsem: {rwsem.value_():x} is free or could not find it's owner reliably"
        )


def get_rwsem_waiters_info(rwsem: Object) -> None:
    """
    Get a summary of rwsem waiters.
    The summary consists of ``struct task_struct *``, pid and type and state of waiters

    :param rwsem: ``struct rw_semaphore *``
    """

    if list_empty(rwsem.wait_list.address_of_()):
        print(f"  rwsem: {rwsem.value_():x} has no waiters.")
        return

    waiter_type = "none"
    print("  The waiters of rwsem are as follows: ")
    for waiter in rwsem_for_each_waiter(rwsem):
        waiter_type = get_rwsem_waiter_type(waiter)
        task = waiter.task
        print(
            f"    ({task.type_.type_name()})0x{task.value_():x}: (pid){task.pid.value_()}: type: {waiter_type} state: {task_state_to_char(task)}"
        )
    print("\n")


def cmd_mutex(args):
    print("##### In cmd_mutex ####")
    for lock_addr in args.locks:
        lock = Object(prog, "struct mutex", address=int(lock_addr, 16))
        if args.info:
            get_mutex_info(lock.address_of_())
        elif args.waiter_list:
            get_mutex_waiters_info(lock.address_of_())
        elif args.waiter_callstack:
            dump_mutex_waiters_call_stack(lock.address_of_())
        elif args.owner_callstack:
            dump_mutex_owner_call_stack(lock.address_of_())


def cmd_semaphore(args):
    print("##### In cmd_semaphore ####")
    for lock_addr in args.locks:
        lock = Object(prog, "struct semaphore", address=int(lock_addr, 16))
        if args.info or args.waiter_list:
            get_semaphore_waiters_info(lock.address_of_())
        elif args.waiter_callstack:
            dump_semaphore_waiters_call_stack(lock.address_of_())


def cmd_rwsem(args):
    print("##### In cmd_rwsem ####")
    for lock_addr in args.locks:
        lock = Object(prog, "struct rw_semaphore", address=int(lock_addr, 16))
        if args.info:
            get_rwsem_info(lock.address_of_())
        elif args.waiter_list:
            get_rwsem_waiters_info(lock.address_of_())
        elif args.waiter_callstack:
            dump_rwsem_waiters_call_stack(lock.address_of_())
        elif args.owner_callstack:
            dump_rwsem_owner_call_stack(lock.address_of_())


def main():
    parser = argparse.ArgumentParser("drgn script to dump lock information")
    sub_parsers = parser.add_subparsers(title="subcommands", dest="subcommand")
    sub_parsers.required = True

    parser_mutex = sub_parsers.add_parser("mutex", help="get mutex info.")
    mutex_arg_group = parser_mutex.add_mutually_exclusive_group()
    mutex_arg_group.add_argument(
        "--info",
        action="store_true",
        help="dump given mutex's info like owner, waiter(s) etc.",
    )
    mutex_arg_group.add_argument(
        "--waiter-list",
        action="store_true",
        help="provide a list, of waiters of given mutex(es)",
    )
    mutex_arg_group.add_argument(
        "--waiter-callstack",
        action="store_true",
        help="provide callstack of all waiters of given mutex(es)",
    )
    mutex_arg_group.add_argument(
        "--owner-callstack",
        action="store_true",
        help="provide callstack of owner of given mutex(es)",
    )
    parser_mutex.add_argument(
        "locks", nargs="*", default=None, help="list of lock addresses"
    )
    parser_mutex.set_defaults(func=cmd_mutex)

    parser_semaphore = sub_parsers.add_parser("semaphore", help="get semaphore info.")
    semaphore_arg_group = parser_semaphore.add_mutually_exclusive_group()
    semaphore_arg_group.add_argument(
        "--info",
        action="store_true",
        help="dump given semaphore's info like waiter(s) etc.",
    )
    semaphore_arg_group.add_argument(
        "--waiter-list",
        action="store_true",
        help="provide a list, of waiters of given semaphore(s)",
    )
    semaphore_arg_group.add_argument(
        "--waiter-callstack",
        action="store_true",
        help="provide callstack of all waiters of given semaphore(s)",
    )
    parser_semaphore.add_argument(
        "locks", nargs="*", default=None, help="list of lock addresses"
    )
    parser_semaphore.set_defaults(func=cmd_semaphore)

    parser_rwsem = sub_parsers.add_parser(
        "rwsem", help="get read-write semaphore info."
    )
    rwsem_arg_group = parser_rwsem.add_mutually_exclusive_group()
    rwsem_arg_group.add_argument(
        "--info",
        action="store_true",
        help="dump given rwsem's info like owner, waiter(s) etc.",
    )
    rwsem_arg_group.add_argument(
        "--waiter-list",
        action="store_true",
        help="provide a list, of waiters of given rwsem(s)",
    )
    rwsem_arg_group.add_argument(
        "--waiter-callstack",
        action="store_true",
        help="provide callstack of all waiters of given rwsem(s)",
    )
    rwsem_arg_group.add_argument(
        "--owner-callstack",
        action="store_true",
        help="provide callstack of owner of given rwsem(s)",
    )
    parser_rwsem.add_argument(
        "locks", nargs="*", default=None, help="list of lock addresses"
    )
    parser_rwsem.set_defaults(func=cmd_rwsem)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
