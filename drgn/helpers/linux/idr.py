# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
IDR
---

The ``drgn.helpers.linux.idr`` module provides helpers for working with the IDR
data structure in :linux:`include/linux/idr.h`. An IDR provides a mapping from
an ID to a pointer.
"""

import operator
from typing import Iterator, Tuple

from _drgn import _linux_helper_idr_find as idr_find_in_radix_tree
from drgn import NULL, IntegerLike, Object, Program, cast, sizeof
from drgn.helpers.linux.radixtree import radix_tree_for_each

__all__ = (
    "idr_find",
    "idr_for_each",
)

_IDR_BITS = 8
_IDR_MASK = (1 << _IDR_BITS) - 1


def _max_idr_shift(prog: Program) -> int:
    return sizeof(prog.type("int")) * 8 - 1


def _max_idr_level(prog: Program) -> int:
    return (_max_idr_shift(prog) + _IDR_BITS - 1) // _IDR_BITS


def _round_up(number: int, multiple: int) -> int:
    return -((-number) // multiple) * multiple


def _idr_max(prog: Program, layers: int) -> int:
    bits = min(layers * _IDR_BITS, _max_idr_shift(prog))
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


def idr_find(idr: Object, id: IntegerLike) -> Object:
    """
    Lookup entry with the given ID in an IDR.

    :param idr: ``struct idr *``
    :param id: ``Entry ID``
    :return: ``void *`` found entry, or NULL if not found.
    """
    id = operator.index(id)

    if hasattr(idr, "idr_rt"):
        return idr_find_in_radix_tree(idr, id)
    else:
        prog = idr.prog_

        if id < 0:
            return NULL(prog, "void *")

        p = idr.top.read_()
        if not p:
            return NULL(prog, "void *")

        n = (p.layer.value_() + 1) * _IDR_BITS
        max_id = _idr_max(prog, p.layer.value_() + 1)
        if n > max_id:
            return NULL(prog, "void *")

        while n > 0 and p:
            n -= _IDR_BITS
            p = p.ary[(id >> n) & _IDR_MASK].read_()

        return cast("void *", p)


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
        voidp_type = idr.prog_.type("void *")

        def aux(p: Object, id: int, n: int) -> Iterator[Tuple[int, Object]]:
            p = p.read_()
            if p:
                if n == 0:
                    yield id, cast(voidp_type, p)
                else:
                    n -= _IDR_BITS
                    for child in p.ary:
                        yield from aux(child, id, n)
                        id += 1 << n

        yield from aux(idr.top, 0, idr.layers.value_() * _IDR_BITS)
