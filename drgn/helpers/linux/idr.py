# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
IDR
---

The ``drgn.helpers.linux.idr`` module provides helpers for working with the IDR
data structure in :linux:`include/linux/idr.h`. An IDR provides a mapping from
an ID to a pointer.
"""

from typing import Iterator, Tuple

from _drgn import _linux_helper_idr_find as idr_find_in_radix_tree
from drgn import NULL, Object, Program, sizeof
from drgn.helpers.linux.radixtree import radix_tree_for_each

__all__ = (
    "idr_find",
    "idr_for_each",
)

IDR_BITS = 8
IDR_MASK = (1 << IDR_BITS) - 1


def _max_idr_shift(prog: Program) -> int:
    return sizeof(prog.type("int")) * 8 - 1


def _max_idr_level(prog: Program) -> int:
    return (_max_idr_shift(prog) + IDR_BITS - 1) // IDR_BITS


def _round_up(number: int, multiple: int) -> int:
    return -((-number) // multiple) * multiple


def _idr_max(prog: Program, layers: int) -> int:
    bits = min(layers * IDR_BITS, _max_idr_shift(prog))
    return (1 << bits) - 1


def _fls(num: int) -> int:
    num_bits = 32
    if num == 0:
        return 0

    for i in range(num_bits):
        if (num & 1) == 1:
            pos = i

        num = num >> 1

    return pos + 1


def idr_find(idr: Object, idval: int) -> Object:
    """
    Lookup entry with the given ID in an IDR.

    :param idr: ``struct idr *``
    :param idval: ``Entry ID``
    :return: ``void *`` found entry, or NULL if not found.
    """
    if idr.prog_.type("struct idr").has_member("idr_rt"):
        return idr_find_in_radix_tree(idr, idval)
    else:
        prog = idr.prog_

        hint = idr.hint.value_()

        if hint:
            prefix = Object(prog, "struct idr_layer", address=hint).prefix.value_()

            if (idval & ~IDR_MASK) == prefix:
                index = idval & IDR_MASK
                p = Object(prog, "struct idr_layer", address=hint).ary.value_()[index]
                return Object(prog, "void *", p)

        if idval < 0:
            return NULL(prog, "void *")

        p = idr.top.value_()
        if p == 0:
            return NULL(prog, "void *")

        idr_layer = Object(prog, "struct idr_layer", address=p)
        n = (idr_layer.layer.value_() + 1) * IDR_BITS
        max_id = _idr_max(prog, idr_layer.layer.value_() + 1)
        if n > max_id:
            return NULL(prog, "void *")

        while n > 0 and p:
            n = n - IDR_BITS
            index = (idval >> n) & IDR_MASK
            p = Object(prog, "struct idr_layer", address=p).ary.value_()[index]

        if p != 0:
            return Object(prog, "void *", p)
        else:
            return NULL(prog, "void *")


def idr_for_each(idr: Object) -> Iterator[Tuple[int, Object]]:
    """
    Iterate over all of the entries in an IDR.

    :param idr: ``struct idr *``
    :return: Iterator of (index, ``void *``) tuples.
    """
    if idr.prog_.type("struct idr").has_member("idr_rt"):
        try:
            base = idr.idr_base.value_()
        except AttributeError:
            base = 0
        for index, entry in radix_tree_for_each(idr.idr_rt.address_of_()):
            yield index + base, entry
    else:
        # kernels < 4.11 don't use radix_tree as idr backend
        prog = idr.prog_
        next_id = 0

        def _idr_get_next(tmp_id: int) -> Tuple[int, Object]:
            pa = [ids for ids in range(_max_idr_level(prog) + 1)]

            pa[0] = idr.top.value_()
            if pa[0] == 0:
                return 0, NULL(prog, "void *")

            pa_idx = 0
            idr_layer = Object(prog, "struct idr_layer", address=pa[0])
            n = (idr_layer.layer.value_() + 1) * IDR_BITS
            max_id = _idr_max(prog, idr_layer.layer.value_() + 1)
            while tmp_id >= 0 and tmp_id <= max_id:
                p = pa[pa_idx]
                while n > 0 and p:
                    n = n - IDR_BITS
                    ary_index = (tmp_id >> n) & IDR_MASK
                    p = Object(prog, "struct idr_layer", address=p).ary.value_()[
                        ary_index
                    ]
                    pa_idx = pa_idx + 1
                    pa[pa_idx] = p

                if p != 0:
                    return tmp_id, Object(prog, "void *", p)

                tmp_id = _round_up(tmp_id + 1, (1 << n))

                while n < _fls(tmp_id):
                    n = n + IDR_BITS
                    pa_idx = pa_idx - 1

            return tmp_id, NULL(prog, "void *")

        next_id = 0
        next_id, entry = _idr_get_next(next_id)
        while entry != NULL(prog, "void *"):
            yield next_id, entry
            next_id = next_id + 1
            next_id, entry = _idr_get_next(next_id)
