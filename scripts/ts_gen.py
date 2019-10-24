# https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html
from abc import abstractmethod
from typing import *
import json
import os
import re
import time
from bs4 import BeautifulSoup

orig_prettify = BeautifulSoup.prettify
r = re.compile(r'^(\s*)', re.MULTILINE)
def prettify(self, encoding=None, formatter="minimal", indent_width=4):
    return r.sub(r'\1' * indent_width, orig_prettify(self, encoding, formatter))
BeautifulSoup.prettify = prettify


INDENT = '    '
FILE_HEADER = "/**\n" \
              " * Auto generated UI5 declarations by Erik Brendel - do not modify\n" \
              " * It can be re-generated from the latest UI5 api docs\n" \
              " */\n\n\n" \
              "declare "
forbidden_words = ['export', 'with', 'as']
forbidden_chars = [' ', '.', ':', '/', '-', '<', '>', '{', '}', '[', ']']


def pp(name: str) -> str:
    if name in forbidden_words:
        return '_' + name
    for char in forbidden_chars:
        name = name.replace(char, '_')
    return name


def capitalize_first(data: str) -> str:
    return data[0].capitalize() + data[1:]


CROSS_LINK = re.compile(r"<a[^>]* href=\"#/api/([a-zA-Z0-9.]+)\"[^>]*>\1</a>")


class Comment:
    text: str

    def __init__(self, text: str = ''):
        self.text = text

    def write(self, f: 'TextIO', indent: str):
        if self.text is None or len(self.text) == 0:
            return
        pretty_text = self.pretty_print(self.clean_text())
        f.write(indent + "/**\n")
        f.write('\n'.join([indent + " * " + line for line in pretty_text.split('\n')]) + "\n")
        f.write(indent + " */\n")

    def clean_text(self) -> str:
        return CROSS_LINK.sub(r"{@link \1}", self.text)

    def pretty_print(self, text: str) -> str:
        # Double curly brackets to avoid problems with .format()
        stripped_markup = text.replace('{', '{{').replace('}', '}}')

        soup = BeautifulSoup(stripped_markup, features="html.parser")
        for img in soup.find_all("img"):
            img.decompose()

        unformatted_tag_list = []

        for i, tag in enumerate(soup.find_all(['span', 'a', 'code'])):
            unformatted_tag_list.append(str(tag))
            tag.replace_with('{' + 'unformatted_tag_list[{0}]'.format(i) + '}')

        return soup.prettify(formatter="minimal").format(unformatted_tag_list=unformatted_tag_list)


class TsType:
    @abstractmethod
    def combine_with(self, other: 'TsType') -> 'CombinedType':
        pass

    @abstractmethod
    def combined_with(self, other: 'TsType') -> 'CombinedType':
        pass

    @abstractmethod
    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        pass

    @abstractmethod
    def combined_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        pass

    @abstractmethod
    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        pass

    @abstractmethod
    def combined_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        pass

    @abstractmethod
    def written(self) -> str:
        pass

    @staticmethod
    def parse(json_types: List) -> 'TsType':
        if len(json_types) == 1:
            return TypeLiteral(TsType.parse_type_name(json_types[0]))
        else:
            return CombinedType([TypeLiteral(TsType.parse_type_name(t)) for t in json_types])

    @staticmethod
    def parse_type_name(json_type):
        name = ''
        if 'name' in json_type:
            name = json_type['name']
        elif 'value' in json_type:
            name = json_type['value']
        else:
            raise Exception("cannot get type name!")
        if name == 'function':
            name = 'Function'
        if name == 'int':
            name = 'number'
        if name == 'float':
            name = 'number'
        if name == 'double':
            name = 'number'
        if name == 'real':
            name = 'number'
        if name == 'array':
            name = 'any[]'
        if name == 'map':
            name = 'any'
        return name


class TypeLiteral(TsType):
    name: str

    def __init__(self, name: str):
        self.name = name

    def combine_with(self, other: 'TsType') -> 'CombinedType':
        return other.combined_with_literal(self)

    def combined_with(self, other: 'TsType') -> 'CombinedType':
        return other.combine_with_literal(self)

    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([self, other])

    def combined_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([other, self])

    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return other.combined_with_literal(self)

    def combined_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return other.combine_with_literal(self)

    def written(self) -> str:
        return self.name


class CombinedType(TsType):
    options: List[TsType]

    def __init__(self, options):
        self.options = options or []

    def combine_with(self, other: 'TsType') -> 'CombinedType':
        return other.combined_with_combined(self)

    def combined_with(self, other: 'TsType') -> 'CombinedType':
        return other.combine_with_combined(self)

    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([*self.options, other])

    def combined_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([other, *self.options])

    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return CombinedType([*self.options, *other.options])

    def combined_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return CombinedType([*other.options, *self.options])

    def written(self) -> str:
        return '(' + " | ".join([o.written() for o in self.options]) + ")"


class Parameter:
    name: str
    description: str
    types: any
    optional: bool
    depth: int
    type: Optional[TsType]

    def __init__(self, json_parameter: json):
        self.name = json_parameter['name']
        self.description = json_parameter.get('description')
        self.types = json_parameter.get('types')
        self.optional = json_parameter.get('optional', False)
        self.depth = json_parameter.get('depth', 0)
        self.type = None
        if 'types' in json_parameter:
            self.type = TsType.parse(json_parameter['types'])

    def written(self) -> str:
        name = pp(self.name)
        if self.optional:
            name += "?"
        if self.type is not None:
            name += ": " + self.type.written()
        return name

    def merge(self, other: 'Parameter'):
        self.name = self.name + 'Or' + capitalize_first(other.name)
        self.type = self.type.combine_with(other.type)


class Method:
    name: str
    description: str
    visibility: str
    parameters: List[Parameter]
    return_type: Optional[TsType]

    def __init__(self, json_method: json):
        self.name = json_method.get('name')
        self.description = json_method.get('description')
        self.visibility = json_method.get('visibility')
        self.parameters = []
        self.return_type = None
        for json_parameter in json_method.get('parameters', []):
            p = Parameter(json_parameter)
            if p.depth == 0:
                self.parameters.append(p)
        if 'returnValue' in json_method and 'types' in json_method['returnValue']:
            self.return_type = TsType.parse(json_method['returnValue']['types'])

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        if self.description is not None:
            Comment(self.description).write(f, indent)
        f.write(indent + pp(self.name) + "(")
        f.write(", ".join([param.written() for param in self.parameters]))
        f.write(")")
        if self.return_type is not None:
            f.write(": " + self.return_type.written())
        f.write(";\n")

    def clean_up(self):
        self.shift_optional_parameters()

    def shift_optional_parameters(self):
        """
        one cannot have optional parameters before required ones, line seen in
        Core.js::attachValidationSuccess(oData?, fnFunction, oListener?);
        So instead, we are shifting the optionality backwards, renaming the parameters to show the ambiguity
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
    description: str

    def __init__(self):
        self.description = None

    def write_comment(self, f: 'TextIO', indent: str):
        Comment(self.description).write(f, indent)


class Class(CodeBlock):
    name: str
    base_class: str
    methods: Dict[str, Method]
    constructor: Method
    is_interface: bool

    def __init__(self, name: str):
        CodeBlock.__init__(self)
        self.name = name
        self.methods = {}
        self.constructor = None
        self.is_interface = False

    def as_interface(self) -> 'Class':
        self.is_interface = True
        return self

    def load(self, json_symbol: json):
        self.description = json_symbol.get('description')
        self.base_class = json_symbol.get('extends')
        for json_method in json_symbol.get('methods', []):
            m = Method(json_method)
            self.methods[m.name] = m
        if 'constructor' in json_symbol:
            self.constructor = Method(json_symbol['constructor'])
            self.constructor.name = 'constructor'

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        self.write_comment(f, indent)
        f.write(indent + self.ns_word() + " " + pp(self.name) + " ")
        if self.base_class is not None:
            f.write("extends " + self.base_class + " ")
        f.write("{\n")
        if self.constructor is not None:
            self.constructor.write(f, indent + INDENT)
        for key in sorted(self.methods):
            self.methods[key].write(f, indent + INDENT)
        f.write(indent + "}\n")

    def ns_word(self):
        if self.is_interface:
            return "interface"
        else:
            return "class"

    def clean_up(self):
        if self.constructor is not None:
            self.constructor.clean_up()
        for name, method in self.methods.items():
            method.clean_up()


class Enum(CodeBlock):
    name: str
    options: List[str]

    def __init__(self, name):
        CodeBlock.__init__(self)
        self.name = name

    def load(self, json_enum):
        self.description = json_enum.get('description')
        options = []
        if 'nodes' in json_enum:
            options = json_enum['nodes']
        if 'properties' in json_enum:
            options = json_enum['properties']
        long_name_length = len(json_enum['name']) + 1
        self.options = [o['name'][long_name_length:] for o in options]

    def clean_up(self):
        pass

    def write(self, f: 'TextIO', indent: str):
        self.write_comment(f, indent)
        f.write(indent + 'enum ' + pp(self.name) + ' {\n')
        for option in self.options:
            f.write(indent + INDENT + option + ",\n")
        f.write(indent + '}\n')


class Typedef:
    name: str

    def __init__(self, name: str):
        self.name = name

    def write(self, f: 'TextIO', indent: str):
        f.write(indent + 'type ' + pp(self.name) + ' = any\n')


class Namespace:
    name: str
    namespaces: Dict[str, 'Namespace']
    classes: Dict[str, Class]
    enums: Dict[str, Enum]
    typedefs: Dict[str, Typedef]

    def __init__(self, name: str):
        self.name = name
        self.namespaces = {}
        self.classes = {}
        self.enums = {}
        self.typedefs = {}

    def resolve_namespace(self, uri: str) -> 'Namespace':
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_namespace(rest)
        else:
            return self.resolve_single_namespace(uri)

    def resolve_single_namespace(self, name) -> 'Namespace':
        if name not in self.namespaces:
            self.namespaces[name] = Namespace(name)
        return self.namespaces[name]

    def resolve_class(self, uri) -> Class:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_class(rest)
        else:
            return self.resolve_single_class(uri)

    def resolve_single_class(self, name) -> Class:
        if name not in self.classes:
            self.classes[name] = Class(name)
        return self.classes[name]

    def resolve_enum(self, uri) -> Enum:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_enum(rest)
        else:
            return self.resolve_single_enum(uri)

    def resolve_single_enum(self, name) -> Enum:
        if name not in self.enums:
            self.enums[name] = Enum(name)
        return self.enums[name]

    def resolve_typedef(self, uri) -> Typedef:
        if '.' in uri:
            [name, rest] = uri.split('.', 1)
            return self.resolve_single_namespace(name).resolve_typedef(rest)
        else:
            return self.resolve_single_typedef(uri)

    def resolve_single_typedef(self, name) -> Typedef:
        if name not in self.typedefs:
            self.typedefs[name] = Typedef(name)
        return self.typedefs[name]

    def write(self, indent: str, name: str):
        if len(self.name) == 0:
            return
        my_name = (name + "." if len(name) > 0 else '') + pp(self.name)
        for key in sorted(self.namespaces):
            self.namespaces[key].write(indent, my_name)

        if len(self.typedefs) + len(self.enums) + len(self.classes) > 0:
            with open('../ts/' + my_name + '.d.ts', 'w', encoding="utf8") as f:
                f.write(FILE_HEADER)
                f.write(indent + "namespace " + my_name + " {\n")
                for name, typedef in self.typedefs.items():
                    typedef.write(f, indent + INDENT)
                for key in sorted(self.enums):
                    self.enums[key].write(f, indent + INDENT)
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
        for name, clazz in self.classes.items():
            clazz.clean_up()


class Declaration:
    root_ns: Namespace = Namespace("root")

    def load(self, json_data: json):
        for json_symbol in json_data['symbols']:
            kind = json_symbol['kind']
            name = json_symbol['name']
            if kind == 'namespace':
                self.root_ns.resolve_namespace(name)
            elif kind == 'class':
                self.root_ns.resolve_class(name).load(json_symbol)
            elif kind == 'enum':
                self.root_ns.resolve_enum(name).load(json_symbol)
            elif kind == 'interface':
                self.root_ns.resolve_class(name).as_interface().load(json_symbol)
            elif kind == 'typedef':
                self.root_ns.resolve_typedef(name)
            else:
                print('unknown kind: ' + kind)

    def save_to(self, directory: str):
        for key in sorted(self.root_ns.namespaces):
            self.root_ns.namespaces[key].write('', '')

    def clean_up(self):
        self.root_ns.clean_up()


if __name__ == "__main__":
    print("This script will generate your typescript declarations, hang tight...")
    decl = Declaration()
    for root, dirs, files in os.walk("../api/"):
        for file in files:
            if '.json' in file and not 'api-index' in file:
                with open(os.path.join(root, file), encoding="utf8") as f:
                    decl.load(json.load(f))
    print("Done loading!")
    print("Now cleaning up... ", end="", flush=True)
    decl.clean_up()
    print("Done!")
    print("Now writing...", end="", flush=True)
    decl.save_to("../ts/")
    print("Done!")
    print("\nAll done!")
    time.sleep(2)
