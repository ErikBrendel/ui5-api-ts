import json
from typing import *

from .ts_typing import *
from .comment import *
from .util_functions import *

import requests
import requests_cache
requests_cache.install_cache(allowable_codes=(200, 404))


ENABLE_SOURCE_LINKS_WITH_LINE_NUMBERS = True
INDENT = '    '
FILE_HEADER = "/**\n" \
              " * Auto generated UI5 declarations by Erik Brendel - do not modify\n" \
              " * It can be re-generated from the latest UI5 api docs\n" \
              " */\n\n\n" \
              "declare "

SOURCE_CACHE = {}


def get_source(lib: str, uri: str) -> str:
    req = requests.get("https://raw.githubusercontent.com/SAP/openui5/master/src/" + lib + "/src/" + uri.replace('.', '/') + ".js")
    try:
        return req.text
    except ValueError:
        print("Cannot access source code for " + lib + "//" + uri)
        return ''


class Parameter:
    name: str
    description: str
    types: any
    optional: bool
    depth: int
    type: Optional[TsType]
    sub_parameters: List['Parameter']

    def __init__(self, json_parameter: json):
        self.name = json_parameter['name']
        self.description = json_parameter.get('description')
        self.types = json_parameter.get('types')
        self.optional = json_parameter.get('optional', False)
        self.depth = json_parameter.get('depth', 0)
        self.type = None
        if 'types' in json_parameter:
            self.type = TsType.parse(json_parameter['types'])
        self.sub_parameters = []

    def written(self) -> str:
        name = pp_name(self.name)
        if self.optional:
            name += "?"
        if self.type is not None:
            name += ": " + self.type.written()
        return name

    def merge(self, other: 'Parameter'):
        self.name = self.name + 'Or' + capitalize_first(other.name)
        self.type = self.type.combine_with(other.type)

    def clean_up(self):
        if self.type is not None and self.type.contains_plain_object() and len(self.sub_parameters) > 0:
            fancy_object = TsType.parse_single('{' + ', '.join([s.written() for s in self.sub_parameters]) + '}')
            self.type = self.type.replace_plain_object_with(fancy_object)

    def trim_by(self, parent_uri: str):
        if self.type is not None:
            self.type.trim_by(parent_uri)

    def add_sub_parameter(self, p: 'Parameter'):
        self.sub_parameters.append(p)


class Method:
    lib: Optional[str]
    parent_uri: str
    name: str
    static: bool
    visibility: Optional[str]
    description: Optional[str]
    parameters: List[Parameter]
    return_type: Optional[TsType]
    needs_function_word: bool

    def __init__(self, parent_uri: str, lib: Optional[str], json_method: json):
        self.lib = lib
        self.parent_uri = parent_uri
        self.name = json_method.get('name', '').split('/')[-1]
        self.static = self.should_be_static()
        self.visibility = json_method.get('visibility')
        self.description = json_method.get('description')
        self.parameters = []
        self.return_type = None
        for json_parameter in json_method.get('parameters', []):
            p = Parameter(json_parameter)
            if p.depth == 0:
                self.parameters.append(p)
            elif p.depth == 1:
                self.parameters[-1].add_sub_parameter(p)
        if 'returnValue' in json_method and 'types' in json_method['returnValue']:
            self.return_type = TsType.parse(json_method['returnValue']['types'])
        self.needs_function_word = False

    def should_be_static(self) -> bool:
        static_begin = self.parent_uri
        if not self.name.startswith(static_begin):
            static_begin = self.parent_uri.split('.')[-1]

        if self.name.startswith(static_begin):
            offset = len(static_begin) + 1
            self.name = self.name[offset:]
            return True
        return False

    def maybe_static_name(self):
        if self.static:
            return self.parent_uri + "." + self.name
        else:
            return self.name

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        if self.description is not None:
            comment = Comment(self.description, self.parent_uri, "/methods/" + self.maybe_static_name())
            for param in self.parameters:
                comment.add_parameter(param.name, param.description)
                for sub in param.sub_parameters:
                    comment.add_parameter(param.name + '.' + sub.name, sub.description)
            comment.lib = self.lib
            comment.source_code_line = self.get_source_line()
            comment.write(f, indent)
        f.write(indent)
        if self.visibility is not None:
            f.write(visibility_parse(self.visibility) + " ")
        if self.static and not self.needs_function_word:
            f.write("static ")
        if self.needs_function_word:
            f.write("function ")
        f.write(pp_name(self.name) + "(")
        f.write(", ".join([param.written() for param in self.parameters]))
        f.write(")")
        if self.return_type is not None:
            f.write(": " + self.return_type.written())
        f.write(";\n")

    def get_source_line(self) -> Optional[int]:
        if not ENABLE_SOURCE_LINKS_WITH_LINE_NUMBERS:
            return None
        if self.lib is None:
            return None
        soure_cache_key = self.lib + "//" + self.parent_uri
        lines = None
        if soure_cache_key in SOURCE_CACHE:
            lines = SOURCE_CACHE[soure_cache_key]
        else:
            source = get_source(self.lib, self.parent_uri)
            if len(source) >= 0 and '404' not in source:
                lines = [l.strip() for l in source.split('\n')]
            SOURCE_CACHE[soure_cache_key] = lines
        if lines is None:
            return None
        # we are searching for e.g. '.create = function'
        target_search = '.' + self.name + ' = function'
        if self.name == 'constructor':
            target_search = 'constructor : function'
        for i, line in zip(range(len(lines)), lines):
            if target_search in line:
                return i + 1
        return None

    def clean_up(self):
        self.shift_optional_parameters()
        for param in self.parameters:
            param.clean_up()
            param.trim_by(self.parent_uri)
        if self.return_type is not None:
            self.return_type.trim_by(self.parent_uri)

    def shift_optional_parameters(self):
        """
        one cannot have optional parameters before required ones, like seen in
        Core.js::attachValidationSuccess(oData?, fnFunction, oListener?);
        So instead, we are shifting the optionality backwards, renaming the parameters to show the ambiguity:
        Core.js::attachValidationSuccess(oDataOrFnFunction, fnFunctionOrOListener?, oListener?);
        """
        if self.num_params() <= 1:
            return
        for i in range(1, self.num_params()):
            if self.parameters[i - 1].optional and not self.parameters[i].optional:
                self.shift_optional_parameter(i)

    def shift_optional_parameter(self, index):
        first_optional_index = self.first_optional_index()
        shift_distance = index - first_optional_index
        assert shift_distance >= 1
        self.parameters[first_optional_index].optional = False
        self.parameters[index].optional = True
        for i in range(first_optional_index, self.num_params()):
            for o in range(1, shift_distance + 1):
                self.merge_parameters(i, i + o)

    def merge_parameters(self, target_index: int, extra_content_index: int):
        if extra_content_index >= self.num_params():
            return
        self.parameters[target_index].merge(self.parameters[extra_content_index])

    def first_optional_index(self) -> int:
        i = 0
        for p in self.parameters:
            if p.optional:
                return i
            i += 1
        return -42

    def num_params(self) -> int:
        return len(self.parameters)


class CodeBlock:
    parent: 'Namespace'
    name: str
    description: Optional[str]
    has_sample: bool
    ux_guide: Optional[Tuple[str, str]]  # (url, displayString)
    lib: Optional[str]

    def __init__(self, name: str, parent: 'Namespace'):
        self.parent = parent
        self.name = name
        self.description = None
        self.has_sample = False
        self.ux_guide = None
        self.lib = None

    def full_uri(self):
        return self.parent.full_uri() + "." + self.name

    def write_comment(self, f: 'TextIO', indent: str):
        if self.description is None:
            return
        comment = Comment(self.description, self.full_uri())
        comment.has_sample = self.has_sample
        comment.ux_guide = self.ux_guide
        comment.lib = self.lib
        comment.write(f, indent)

    def set_lib(self, lib: str) -> 'CodeBlock':
        self.lib = lib
        return self


class Class(CodeBlock):
    name: str
    base_class: Optional[TsType]
    interfaces: []
    methods: Dict[str, Method]
    constructor: Optional[Method]
    is_interface: bool

    def __init__(self, name: str, parent: 'Namespace'):
        CodeBlock.__init__(self, name, parent)
        self.methods = {}
        self.constructor = None
        self.is_interface = False

    def as_interface(self) -> 'Class':
        self.is_interface = True
        return self

    def load(self, json_symbol: json):
        self.description = json_symbol.get('description')
        self.base_class = None
        if 'extends' in json_symbol:
            self.base_class = TsType.parse_single(json_symbol.get('extends'))
        self.interfaces = json_symbol.get('implements', [])
        for json_method in json_symbol.get('methods', []):
            m = Method(self.full_uri(), self.lib, json_method)
            self.methods[m.name] = m
        if 'constructor' in json_symbol:
            self.constructor = Method(self.full_uri(), self.lib, json_symbol['constructor'])
            self.constructor.name = 'constructor'
        if 'hasSample' in json_symbol and json_symbol['hasSample']:
            self.has_sample = True
        if 'uxGuidelinesLink' in json_symbol:
            self.ux_guide = (json_symbol['uxGuidelinesLink'], json_symbol['uxGuidelinesLinkText'])

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        self.write_comment(f, indent)
        f.write(indent + self.ns_word() + " " + pp_name(self.name) + " ")
        if self.base_class is not None:
            f.write("extends " + self.base_class.written() + " ")
        if len(self.interfaces) > 0:
            f.write("implements " + ", ".join(self.interfaces) + " ")
        f.write("{\n")
        if self.constructor is not None:
            self.constructor.write(f, indent + INDENT)
        for key in sorted(self.methods):
            self.methods[key].write(f, indent + INDENT)
        f.write(indent + "}\n")

    def ns_word(self):
        if self.is_interface:
            if any([m.static for m in self.methods.values()]):
                # since typescript doesn't want static methods in interfaces, we just make them classes
                return "class /* interface */"
            else:
                return "interface"
        else:
            return "class"

    def clean_up(self):
        if self.base_class is not None:
            self.base_class.trim_by(self.full_uri())
        if self.constructor is not None:
            self.constructor.clean_up()
        for name, method in self.methods.items():
            method.clean_up()
            if self.is_interface:
                method.visibility = None


class Enum(CodeBlock):
    options: List[Tuple[str, str]]  # (name, comment)

    def __init__(self, name, parent: 'Namespace'):
        CodeBlock.__init__(self, name, parent)

    def load(self, json_enum):
        self.description = json_enum.get('description')
        options = []
        if 'nodes' in json_enum:
            options = json_enum['nodes']
        if 'properties' in json_enum:
            options = json_enum['properties']
        long_name_length = len(json_enum['name']) + 1
        self.options = [(o['name'][long_name_length:], o.get('description')) for o in options]

    def clean_up(self):
        pass

    def write(self, f: 'TextIO', indent: str):
        self.write_comment(f, indent)
        f.write(indent + 'enum ' + pp_name(self.name) + ' {\n')
        for (name, description) in self.options:
            if description is not None:
                Comment(description).write(f, indent + INDENT)
            f.write(indent + INDENT + name + ",\n")
        f.write(indent + '}\n')


class Typedef(CodeBlock):
    type: TsType

    def __init__(self, name: str, parent: 'Namespace'):
        CodeBlock.__init__(self, name, parent)
        self.type = TsType.parse_single('any')

    def write(self, f: 'TextIO', indent: str):
        self.write_comment(f, indent)
        f.write(indent + 'type ' + pp_name(self.name) + ' = ' + self.type.written() + '\n')

    def load(self, json_typedef):
        meta = json_typedef.get('ui5-metadata', {})
        if 'basetype' in meta:
            self.type = TsType.parse_single(meta['basetype'])
        if 'pattern' in meta:
            self.description = 'Needs to follow this regex: ' + meta['pattern']


class Namespace:
    parent: Optional['Namespace']
    name: str
    namespaces: Dict[str, 'Namespace']
    classes: Dict[str, Class]
    enums: Dict[str, Enum]
    typedefs: Dict[str, Typedef]
    methods: Dict[str, Method]

    def __init__(self, name: str, parent: 'Namespace' = None):
        self.parent = parent
        self.name = name
        self.namespaces = {}
        self.classes = {}
        self.enums = {}
        self.typedefs = {}
        self.methods = {}

    def resolve_namespace(self, uri: str) -> 'Namespace':
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_namespace(rest)
        else:
            return self.resolve_single_namespace(uri)

    def resolve_single_namespace(self, name) -> 'Namespace':
        if name not in self.namespaces:
            self.namespaces[name] = Namespace(name, self)
        return self.namespaces[name]

    def resolve_class(self, uri) -> Class:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_class(rest)
        else:
            return self.resolve_single_class(uri)

    def resolve_single_class(self, name) -> Class:
        if name not in self.classes:
            self.classes[name] = Class(name, self)
        return self.classes[name]

    def resolve_enum(self, uri) -> Enum:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_enum(rest)
        else:
            return self.resolve_single_enum(uri)

    def resolve_single_enum(self, name) -> Enum:
        if name not in self.enums:
            self.enums[name] = Enum(name, self)
        return self.enums[name]

    def resolve_typedef(self, uri) -> Typedef:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_typedef(rest)
        else:
            return self.resolve_single_typedef(uri)

    def resolve_single_typedef(self, name) -> Typedef:
        if name not in self.typedefs:
            self.typedefs[name] = Typedef(name, self)
        return self.typedefs[name]

    def resolve_method(self, uri, json_method) -> Method:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_method(rest, json_method)
        else:
            return self.resolve_single_method(json_method)

    def resolve_single_method(self, json_method) -> Method:
        m = Method(self.full_uri(), None, json_method)
        name = m.name
        if name not in self.methods:
            m.needs_function_word = True
            self.methods[name] = m
        return self.methods[name]

    def write(self, indent: str, name: str, directory: str):
        if len(self.name) == 0:
            return
        my_name = (name + "." if len(name) > 0 else '') + pp_name(self.name)
        for key in sorted(self.namespaces):
            self.namespaces[key].write(indent, my_name, directory)

        if len(self.typedefs) + len(self.enums) + len(self.classes) + len(self.methods) > 0:
            with open(directory + my_name + '.d.ts', 'w', encoding="utf8") as f:
                f.write(FILE_HEADER)
                f.write(indent + "namespace " + my_name + " {\n")
                for name, typedef in self.typedefs.items():
                    typedef.write(f, indent + INDENT)
                for key in sorted(self.enums):
                    self.enums[key].write(f, indent + INDENT)
                for key in sorted(self.methods):
                    self.methods[key].write(f, indent + INDENT)
                for key in sorted(self.classes):
                    self.classes[key].write(f, indent + INDENT)
                f.write(indent + "}\n")

    def clean_up(self):
        for name in list(self.namespaces.keys()):
            if ' ' in name:
                self.namespaces.pop(name)
        for name, ns in self.namespaces.items():
            ns.clean_up()
        for name, enum in self.enums.items():
            enum.clean_up()
        for name, method in self.methods.items():
            method.clean_up()
        for name, clazz in self.classes.items():
            clazz.clean_up()

    def full_uri(self):
        if self.parent is None or self.parent.full_uri() == 'root':
            return self.name
        return self.parent.full_uri() + "." + self.name

    def load(self, json_namespace):
        for json_method in json_namespace.get('methods', {}):
            self.resolve_single_method(json_method).visibility = None


class Declaration:
    root_ns: Namespace = Namespace("root")

    def load(self, json_data: json, lib_name: str):
        for json_symbol in json_data['symbols']:
            kind = json_symbol['kind']
            name: str = pp_class_name(json_symbol['name'])
            meta = json_symbol.get('ui5-metadata', {})
            if meta.get('stereotype', '') == 'datatype':
                kind = 'typedef'
            if kind == 'namespace':
                self.root_ns.resolve_namespace(name).load(json_symbol)
            elif kind == 'class':
                self.root_ns.resolve_class(name).set_lib(lib_name).load(json_symbol)
            elif kind == 'enum':
                self.root_ns.resolve_enum(name).set_lib(lib_name).load(json_symbol)
            elif kind == 'interface':
                self.root_ns.resolve_class(name).set_lib(lib_name).as_interface().load(json_symbol)
            elif kind == 'typedef':
                self.root_ns.resolve_typedef(name).set_lib(lib_name).load(json_symbol)
            elif kind == 'function':
                self.root_ns.resolve_method(name, json_symbol).visibility = None
            else:
                print('unknown kind: ' + kind)

    def save_to(self, directory: str):
        for key in sorted(self.root_ns.namespaces):
            self.root_ns.namespaces[key].write('', '', directory)

    def clean_up(self):
        self.root_ns.clean_up()
