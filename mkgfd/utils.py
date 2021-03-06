#! /usr/bin/env python

from argparse import ArgumentTypeError
from datetime import date, datetime, time
from re import match

from rdflib.graph import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from mkgfd.multimodal import XSD_DATEFRAG, XSD_DATETIME, XSD_NUMERIC, XSD_STRING
from mkgfd.structures import TypeVariable, DataTypeVariable, MultiModalNode, ObjectTypeVariable
from mkgfd.timeutils import gFrag_to_days


def cast_xsd(node, dtype):
    node = node.toPython()
    if dtype in XSD_NUMERIC:
        try:
            node = float(node)
        except ValueError:
            pass
    elif dtype in XSD_DATETIME:
        try:
            if isinstance(node, date):
                node = datetime.combine(node, time()).isoformat()
            node = datetime.fromisoformat(node)
        except ValueError:
            pass
    elif dtype in XSD_DATEFRAG:
        try:
            node = gFrag_to_days(str(node), dtype)
        except ValueError:
            pass
    elif dtype in XSD_STRING:
        try:
            node = str(node).strip().lower()
        except ValueError:
            pass

    return node

def generate_label_map(g):
    label_map = DictDefault(str())
    for e, _, l in g.triples((None, RDFS.label, None)):
        label_map[e] = l

    return label_map

def generate_data_type_map(g):
    data_type_map = {'object-to-type': DictDefault(None),
                     'type-to-object': DictDefault(set())}
    for o in g.objects():
        if not isinstance(o, Literal):
            continue

        dtype = o.datatype
        if dtype is None:
            dtype = XSD.string if o.language != None else XSD.anyType

        if dtype not in data_type_map.keys():
            data_type_map['type-to-object'][dtype] = set()

        data_type_map['type-to-object'][dtype].add(o)
        data_type_map['object-to-type'][o] = dtype

    return data_type_map

def generate_object_type_map(g):
    object_type_map = {'object-to-type': DictDefault(set()),
                       'type-to-object': DictDefault(set())}
    for e in g.subjects():
        if not isinstance(e, URIRef):
            continue

        ctypes = list(g.objects(e, RDF.type))
        if len(ctypes) <= 0:
            ctypes.append(RDFS.Class)
        for ctype in ctypes:
            if ctype not in object_type_map['type-to-object'].keys():
                object_type_map['type-to-object'][ctype] = set()
            if e not in object_type_map['object-to-type'].keys():
                object_type_map['object-to-type'][e] = set()

            object_type_map['type-to-object'][ctype].add(e)
            object_type_map['object-to-type'][e].add(ctype)

    return object_type_map

def generate_predicate_map(g):
    predicate_map = dict()

    for lhs, predicate, rhs in g.triples((None, None, None)):
        if predicate not in predicate_map.keys():
            predicate_map[predicate] = {'forwards': DictDefault(set()),
                                        'backwards': DictDefault(set())}

        if lhs not in predicate_map[predicate]['forwards'].keys():
            predicate_map[predicate]['forwards'][lhs] = {rhs}
        else:
            predicate_map[predicate]['forwards'][lhs].add(rhs)

        if rhs not in predicate_map[predicate]['backwards'].keys():
            predicate_map[predicate]['backwards'][rhs] = {lhs}
        else:
            predicate_map[predicate]['backwards'][rhs].add(lhs)

    return predicate_map

def predicate_frequency(predicate_map,
                        assertion,
                        assertion_domain):
    return len(assertion_domain &
               predicate_map[assertion.predicate]['forwards'].keys())

class DictDefault(dict):
    """ DictDefault class

    Extension of a dictionary that returns a default value when an unknown key
    is requested. Differs from DefaultDict in that unknown keys are not stored
    upon request.
    """
    # not necessary, just a memory optimization
    __slots__ = ['_default']

    def __init__(self, default, *args, **kwargs):
        self._default = default
        super().__init__(*args, **kwargs)

    def __missing__(self, key):
        return self._default

def isEquivalent(assertionA, assertionB, cache):
    if (not (isinstance(assertionA.lhs, ObjectTypeVariable) and\
             isinstance(assertionB.lhs, ObjectTypeVariable) and\
             assertionA.lhs.type == assertionB.lhs.type)) or\
       assertionA.predicate != assertionB.predicate:
        return False

    # rhs is the same resource, or same type var, 
    # or one is a instance of the other's type var
    return (assertionA.rhs == assertionB.rhs or\
            (isinstance(assertionA.rhs, TypeVariable) and\
             isinstance(assertionB.rhs, TypeVariable) and\
             assertionA.rhs.type == assertionB.rhs.type) or\
            isSameType(assertionA.rhs, assertionB.rhs, cache) or\
            isSameType(assertionB.rhs, assertionA.rhs, cache))

def isSameType(resourceA, resourceB, cache):
    if isinstance(resourceA, ObjectTypeVariable):
        if (type(resourceB) is URIRef and\
            resourceB in cache.object_type_map['object-to-type'].keys()):
            for ctype in cache.object_type_map['object-to-type'][resourceB]:
                if ctype == resourceA.type:
                    return True

    if isinstance(resourceA, DataTypeVariable)\
       or isinstance(resourceA, MultiModalNode):
        if (type(resourceB) is Literal and\
            resourceB in cache.data_type_map['object-to-type'].keys() and\
            resourceA.type == cache.data_type_map['object-to-type'][resourceB]):
            return True

    return False

def integerRangeArg(string):
    m = match(r'(\d+)(?:-(\d+))?$', string)
    if not m:
        raise ArgumentTypeError("'" + string + "' is not a range of number. Expected forms like '0-5' or '2'.")

    if not m.group(2):
        return range(0, int(m.group(1)))

    return range(int(m.group(1)), int(m.group(2)))
