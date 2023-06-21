#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: LGPL-2.1-or-later

import argparse
import itertools
import sys
from typing import TextIO

from codegen_utils import c_string_literal

DWARF_INDEX_SECTIONS = (
    ".debug_info",
    ".debug_types",
    ".debug_abbrev",
    ".debug_str",
    ".debug_str_offsets",
    ".debug_line",
    ".debug_line_str",
)

CACHED_SECTIONS = (
    ".debug_addr",
    ".debug_frame",
    ".eh_frame",
    ".debug_loc",
    ".debug_loclists",
)

UNCACHED_SECTIONS = (
    ".text",
    ".got",
)


def section_enumerator_name(section_name: str) -> str:
    return "DRGN_SCN_" + section_name.lstrip(".").upper()


def gen_elf_sections_h(out_file: TextIO) -> None:
    out_file.write(
        """\
/* Generated by libdrgn/build-aux/gen_elf_sections.py -H. */

#ifndef DRGN_ELF_SECTIONS_H
#define DRGN_ELF_SECTIONS_H

/**
 * Identifiers for important ELF sections so that they can be referenced by
 * index rather than name.
 */
enum drgn_section_index {
"""
    )
    for section_name in DWARF_INDEX_SECTIONS:
        out_file.write(f"\t{section_enumerator_name(section_name)},\n")
    out_file.write(
        """\
	/** Indices less than this are cached when the module is loaded. */
	DRGN_SECTION_INDEX_NUM_PRECACHE,
"""
    )

    for i, section_name in enumerate(CACHED_SECTIONS):
        if i == 0:
            out_file.write(
                f"\t{section_enumerator_name(section_name)} = DRGN_SECTION_INDEX_NUM_PRECACHE,\n"
            )
        else:
            out_file.write(f"\t{section_enumerator_name(section_name)},\n")
    out_file.write(
        """\
	/** Indices less than this may have their data cached. */
	DRGN_SECTION_INDEX_NUM_DATA,
"""
    )

    for i, section_name in enumerate(UNCACHED_SECTIONS):
        if i == 0:
            out_file.write(
                f"\t{section_enumerator_name(section_name)} = DRGN_SECTION_INDEX_NUM_DATA,\n"
            )
        else:
            out_file.write(f"\t{section_enumerator_name(section_name)},\n")
    out_file.write(
        """\
	/** Number of section indices. */
	DRGN_SECTION_INDEX_NUM
};

#endif /* DRGN_ELF_SECTIONS_H */
"""
    )


def gen_drgn_section_name_to_index_inc_strswitch(out_file: TextIO) -> None:
    debug_sections = []
    non_debug_sections = []
    for section_name in itertools.chain(
        DWARF_INDEX_SECTIONS, CACHED_SECTIONS, UNCACHED_SECTIONS
    ):
        if section_name.startswith(".debug_"):
            debug_sections.append(section_name)
        else:
            non_debug_sections.append(section_name)

    out_file.write(
        """\
/* Generated by libdrgn/build-aux/gen_elf_sections.py. */

static enum drgn_section_index drgn_debug_section_name_to_index(const char *name, size_t len)
{
	@memswitch (name, len)@
"""
    )
    for section_name in debug_sections:
        out_file.write(f"\t@case {c_string_literal(section_name[len('.debug_'):])}@\n")
        out_file.write(f"\t\treturn {section_enumerator_name(section_name)};\n")
    out_file.write(
        """\
	@default@
		return DRGN_SECTION_INDEX_NUM;
	@endswitch@
}

static enum drgn_section_index drgn_non_debug_section_name_to_index(const char *name)
{
	@strswitch (name)@
"""
    )
    for section_name in non_debug_sections:
        out_file.write(f"\t@case {c_string_literal(section_name)}@\n")
        out_file.write(f"\t\treturn {section_enumerator_name(section_name)};\n")
    out_file.write(
        """\
	@default@
		return DRGN_SECTION_INDEX_NUM;
	@endswitch@
}
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--header", "-H", action="store_true", help="generate header file"
    )
    args = parser.parse_args()

    if args.header:
        gen_elf_sections_h(sys.stdout)
    else:
        gen_drgn_section_name_to_index_inc_strswitch(sys.stdout)


if __name__ == "__main__":
    main()
