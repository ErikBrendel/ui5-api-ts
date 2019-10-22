# https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html
from abc import abstractmethod
from typing import *
import json
import os

INDENT = '    '
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


class TsType:
    @abstractmethod
    def combine_with(self, other: 'TsType') -> 'CombinedType':
        pass

    @abstractmethod
    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        pass

    @abstractmethod
    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
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
        if name == 'array':
            name = 'any[]'
        return name


class TypeLiteral(TsType):
    name: str

    def __init__(self, name: str):
        self.name = name

    def combine_with(self, other: 'TsType') -> 'CombinedType':
        return other.combine_with_literal(self)

    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([self, other])

    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return other.combine_with_literal(self)

    def written(self) -> str:
        return self.name


class CombinedType(TsType):
    options: List[TsType]

    def __init__(self, options):
        self.options = options or []

    def combine_with(self, other: 'TsType') -> 'CombinedType':
        return other.combine_with_combined(self)

    def combine_with_literal(self, other: 'TypeLiteral') -> 'CombinedType':
        return CombinedType([*self.options, other])

    def combine_with_combined(self, other: 'CombinedType') -> 'CombinedType':
        return CombinedType([*self.options, *other.options])

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
        # TODO type merging also!


class Method:
    name: str
    description: str
    visibility: str
    parameters: List[Parameter]
    returnType: TsType

    def __init__(self, json_method: json):
        self.name = json_method.get('name')
        self.visibility = json_method.get('visibility')
        self.description = json_method.get('description')
        self.parameters = []
        for json_parameter in json_method.get('parameters', []):
            p = Parameter(json_parameter)
            if p.depth == 0:
                self.parameters.append(p)

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        f.write(indent + pp(self.name) + "(")
        f.write(", ".join([param.written() for param in self.parameters]))
        f.write(");\n")

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


class Class:
    name: str
    methods: Dict[str, Method]
    constructor: Method

    def __init__(self, name: str):
        self.name = name
        self.methods = {}
        self.constructor = None

    def load(self, json_symbol: json):
        for json_method in json_symbol.get('methods', []):
            m = Method(json_method)
            self.methods[m.name] = m
        if 'constructor' in json_symbol:
            self.constructor = Method(json_symbol['constructor'])
            self.constructor.name = 'constructor'

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        f.write(indent + "class " + pp(self.name) + " {\n")
        if self.constructor is not None:
            self.constructor.write(f, indent + INDENT)
        for key in sorted(self.methods):
            self.methods[key].write(f, indent + INDENT)
        f.write(indent + "}\n")

    def clean_up(self):
        if self.constructor is not None:
            self.constructor.clean_up()
        for name, method in self.methods.items():
            method.clean_up()


class Enum:
    name: str
    options: List[str]

    def __init__(self, name):
        self.name = name

    def load(self, json_enum):
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
        f.write(indent + 'enum ' + pp(self.name) + ' {\n')
        for option in self.options:
            f.write(indent + INDENT + option + ",\n")
        f.write(indent + '}\n')

class Namespace:
    name: str
    namespaces: Dict[str, 'Namespace']
    classes: Dict[str, Class]
    enums: Dict[str, Enum]

    def __init__(self, name: str):
        self.name = name
        self.namespaces = {}
        self.classes = {}
        self.enums = {}

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

    def write(self, f: 'TextIO', indent: str):
        if len(self.name) == 0:
            return
        f.write(indent + "namespace " + pp(self.name) + " {\n")
        for key in sorted(self.namespaces):
            self.namespaces[key].write(f, indent + INDENT)
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
            else:
                print('unknown kind: ' + kind)

    def save_to(self, directory: str):
        with open(directory + 'ui5.d.ts', 'w') as f:
            f.write("/**\n"
                    " * Auto generated UI5 declarations by Erik Brendel - do not modify\n"
                    " * It can be re-generated from the latest UI5 api docs\n"
                    " */\n\n\n")
            for key in sorted(self.root_ns.namespaces):
                f.write('declare ')
                self.root_ns.namespaces[key].write(f, '')

    def clean_up(self):
        self.root_ns.clean_up()


if __name__ == "__main__":
    decl = Declaration()
    for root, dirs, files in os.walk("../api/"):
        for file in files:
            if '.json' in file and not 'api-index' in file:
                with open(os.path.join(root, file), encoding="utf8") as f:
                    decl.load(json.load(f))
    print("Done loading, now cleaning up...")
    decl.clean_up()
    print("Done cleaning up, now writing...")
    decl.save_to("../ts/")
    print("All done!")
