// Copyright (c) Meta Platforms, Inc. and affiliates.
// SPDX-License-Identifier: LGPL-2.1-or-later

#include <inttypes.h>

#include "drgnpy.h"

PyObject *Symbol_wrap(struct drgn_symbol *sym, Program *prog)
{
	Symbol *ret = call_tp_alloc(Symbol);
	if (ret) {
		ret->sym = sym;
		ret->prog = prog;
		Py_INCREF(prog);
	}
	return (PyObject *)ret;
}

static void Symbol_dealloc(Symbol *self)
{
	drgn_symbol_destroy(self->sym);
	Py_XDECREF(self->prog);
	Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *Symbol_richcompare(Symbol *self, PyObject *other, int op)
{
	if (!PyObject_TypeCheck(other, &Symbol_type) ||
	    (op != Py_EQ && op != Py_NE))
		Py_RETURN_NOTIMPLEMENTED;
	bool ret = drgn_symbol_eq(self->sym, ((Symbol *)other)->sym);
	if (op == Py_NE)
		ret = !ret;
	Py_RETURN_BOOL(ret);
}

static PyObject *Symbol_get_name(Symbol *self, void *arg)
{
	return PyUnicode_FromString(drgn_symbol_name(self->sym));
}

static PyObject *Symbol_get_address(Symbol *self, void *arg)
{
	return PyLong_FromUint64(drgn_symbol_address(self->sym));
}

static PyObject *Symbol_get_size(Symbol *self, void *arg)
{
	return PyLong_FromUint64(drgn_symbol_size(self->sym));
}

static PyObject *Symbol_get_binding(Symbol *self, void *arg)
{
	return PyObject_CallFunction(SymbolBinding_class, "k",
				     (unsigned long)drgn_symbol_binding(self->sym));
}

static PyObject *Symbol_get_kind(Symbol *self, void *arg)
{
	return PyObject_CallFunction(SymbolKind_class, "k",
				     (unsigned long)drgn_symbol_kind(self->sym));
}

static PyObject *Symbol_repr(Symbol *self)
{
	_cleanup_pydecref_ PyObject *name =
		PyUnicode_FromString(drgn_symbol_name(self->sym));
	if (!name)
		return NULL;
	_cleanup_pydecref_ PyObject *binding = Symbol_get_binding(self, NULL);
	if (!binding)
		return NULL;
	_cleanup_pydecref_ PyObject *kind = Symbol_get_kind(self, NULL);
	if (!kind)
		return NULL;

	char address[19], size[19];
	sprintf(address, "0x%" PRIx64, drgn_symbol_address(self->sym));
	sprintf(size, "0x%" PRIx64, drgn_symbol_size(self->sym));
	return PyUnicode_FromFormat("Symbol(name=%R, address=%s, size=%s, binding=%R, kind=%R)",
				    name, address, size, binding, kind);
}

static PyGetSetDef Symbol_getset[] = {
	{"name", (getter)Symbol_get_name, NULL, drgn_Symbol_name_DOC},
	{"address", (getter)Symbol_get_address, NULL, drgn_Symbol_address_DOC},
	{"size", (getter)Symbol_get_size, NULL, drgn_Symbol_size_DOC},
	{"binding", (getter)Symbol_get_binding, NULL, drgn_Symbol_binding_DOC},
	{"kind", (getter)Symbol_get_kind, NULL, drgn_Symbol_kind_DOC},
	{},
};

PyTypeObject Symbol_type = {
	PyVarObject_HEAD_INIT(NULL, 0)
	.tp_name = "_drgn.Symbol",
	.tp_basicsize = sizeof(Symbol),
	.tp_dealloc = (destructor)Symbol_dealloc,
	.tp_repr = (reprfunc)Symbol_repr,
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc = drgn_Symbol_DOC,
	.tp_richcompare = (richcmpfunc)Symbol_richcompare,
	.tp_getset = Symbol_getset,
};
