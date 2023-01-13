# Copyright (c) 2022, Oracle and/or its affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

from drgn.helpers.linux.idr import idr_for_each
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.percpu import per_cpu
from drgn.helpers.linux.pid import for_each_task

from drgn.helpers.linux.workqueue import (
    find_workqueue,
    for_each_cpu_worker_pool,
    for_each_pool,
    for_each_pool_worker,
    for_each_worker,
    for_each_workqueue,
)
from tests.linux_kernel import LinuxKernelTestCase


def system_workqueue_names(prog):
    # Pick some global workqueues that will always exist
    return {
        prog["system_wq"].name.string_(),
        prog["system_unbound_wq"].name.string_(),
    }


class TestWorkqueue(LinuxKernelTestCase):
    def test_for_each_workqueue(self):
        # The found workqueue names should be a superset of the test names.
        self.assertGreaterEqual(
            {wq.name.string_() for wq in for_each_workqueue(self.prog)},
            system_workqueue_names(self.prog),
        )

    def test_for_each_pool(self):
        self.assertIn(
            per_cpu(self.prog["cpu_worker_pools"], 0)[0].address_of_(),
            for_each_pool(self.prog),
        )

    def test_for_each_worker(self):
        kworkers = [
            task.value_()
            for task in for_each_task(self.prog)
            if task.comm.string_().decode().startswith("kworker")
        ]
        self.assertEqual(
            [worker.task.value_() for worker in for_each_worker(self.prog)].sort(),
            kworkers.sort(),
        )

    def test_for_each_pool_worker(self):
        test_pool = per_cpu(self.prog["cpu_worker_pools"], 0)[0].address_
        kworkers = [
            workers.value_()
            for workers in for_each_worker(self.prog)
            if workers.pool.value_() == test_pool
        ]
        pool_kworkers = [
            workers.value_()
            for workers in for_each_pool_worker(
                per_cpu(self.prog["cpu_worker_pools"], 0)[0].address_of_()
            )
        ]
        self.assertEqual(kworkers.sort(), pool_kworkers.sort())

    def test_for_each_cpu_worker_pool(self):
        cpu0_worker_pools = [
            per_cpu(self.prog["cpu_worker_pools"], 0)[i].address_ for i in [0, 1]
        ]
        worker_pools = [
            worker_pool.value_()
            for worker_pool in for_each_cpu_worker_pool(self.prog, 0)
        ]
        self.assertEqual(worker_pools, cpu0_worker_pools)

    def test_find_workqueue(self):
        workqueue_names = system_workqueue_names(self.prog)
        for name in workqueue_names:
            workqueue = find_workqueue(self.prog, name)
            self.assertEqual(name, workqueue.name.string_())
