# Copyright (c) 2022, Oracle and/or its affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

from drgn.helpers.linux.cpumask import for_each_online_cpu
from drgn.helpers.linux.percpu import per_cpu, per_cpu_ptr
from drgn.helpers.linux.pid import for_each_task
from drgn.helpers.linux.workqueue import (
    find_worker_executing_work,
    find_workqueue,
    for_each_cpu_worker_pool,
    for_each_pending_work,
    for_each_pending_work_in_pool,
    for_each_pending_work_of_pwq,
    for_each_pending_work_on_cpu,
    for_each_pool,
    for_each_pool_worker,
    for_each_pwq,
    for_each_worker,
    for_each_workqueue,
    get_work_pool,
    get_work_pwq,
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

    def test_for_each_pwq(self):
        wq = find_workqueue(self.prog, "drgn_test_wq")
        # Since "drgn_test_wq" is a bound workqueue, list pwqs
        # should contain only per-cpu pwqs i.e cpu_pwqs
        pwqs = [pwq.value_() for pwq in for_each_pwq(wq)]
        cpu_pwqs = [
            per_cpu_ptr(wq.cpu_pwqs, cpu).value_()
            for cpu in for_each_online_cpu(self.prog)
        ]
        self.assertEqual(pwqs.sort(), cpu_pwqs.sort())

    def test_for_each_pending_work(self):
        all_works = [work.value_() for work in for_each_pending_work(self.prog)]
        test_works = [self.prog["drgn_test_works"][i].address_ for i in range(5)]
        self.assertGreaterEqual(all_works, test_works)

    def test_for_each_pending_work_on_cpu(self):
        all_works = [
            work.value_() for work in for_each_pending_work_on_cpu(self.prog, 0)
        ]
        test_works = [self.prog["drgn_test_works"][i].address_ for i in range(5)]
        self.assertGreaterEqual(all_works, test_works)

    def test_for_each_pending_work_in_pool(self):
        pool = per_cpu(self.prog["cpu_worker_pools"], 0)[0].address_of_()
        all_works_in_pool = [
            work.value_() for work in for_each_pending_work_in_pool(pool)
        ]
        test_works = [self.prog["drgn_test_works"][i].address_ for i in range(5)]
        self.assertGreaterEqual(all_works_in_pool, test_works)

    def test_for_each_pending_work_of_pwq(self):
        wq = find_workqueue(self.prog, "drgn_test_wq")
        cpu_pwqs_0 = per_cpu_ptr(wq.cpu_pwqs, 0)
        all_works_of_pwq = [
            work.value_() for work in for_each_pending_work_of_pwq(cpu_pwqs_0)
        ]
        test_works = [self.prog["drgn_test_works"][i].address_ for i in range(5)]
        self.assertEqual(all_works_of_pwq, test_works)

    def test_get_work_pwq(self):
        wq = find_workqueue(self.prog, "drgn_test_wq")
        cpu_pwqs_0 = per_cpu_ptr(wq.cpu_pwqs, 0)
        cpu_pwqs_1 = per_cpu_ptr(wq.cpu_pwqs, 1)
        work = self.prog["drgn_test_works"][0].address_of_()
        pwq = get_work_pwq(work)
        self.assertEqual(pwq, cpu_pwqs_0)
        self.assertNotEqual(pwq, cpu_pwqs_1)

    def test_get_work_pool(self):
        work = self.prog["drgn_test_works"][0].address_of_()
        pool = get_work_pool(work)
        pool_0 = per_cpu(self.prog["cpu_worker_pools"], 0)[0].address_of_()
        pool_1 = per_cpu(self.prog["cpu_worker_pools"], 1)[0].address_of_()
        self.assertEqual(pool, pool_0)
        self.assertNotEqual(pool, pool_1)

    def test_find_worker_executing_work(self):
        blocker_work = self.prog["drgn_test_blocker_work"].address_of_()
        worker = find_worker_executing_work(blocker_work)
        self.assertEqual(worker.current_work, blocker_work)
