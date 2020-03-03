from abc import abstractmethod
from typing import *
import re
from scripts.util.UtilFunctions import *


OBJ_MAP = re.compile(r"Object\.<(.+),(.+)>")


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
    def trim_by(self, base_uri: str):
        pass

    @abstractmethod
    def written(self) -> str:
        pass

    @abstractmethod
    def contains_plain_object(self):
        pass

    @abstractmethod
    def replace_plain_object_with(self, fancy_object: 'TsType') -> 'TsType':
        pass

    @staticmethod
    def parse_single(type: str):
        return TypeLiteral(TsType.parse_type_name({"name": type}))

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
        name = pp_type(name)
        if name == 'function':
            name = 'Function'
        if name == 'int':
            name = 'number/*int*/'
        if name == 'int[]':
            name = 'number[]/*int[]*/'
        if name == 'float':
            name = 'number'
        if name == 'float[]':
            name = 'number[]'
        if name == 'double':
            name = 'number'
        if name == 'double[]':
            name = 'number[]'
        if name == 'real':
            name = 'number'
        if name == 'real[]':
            name = 'number[]'
        if name == 'date':
            name = 'Date'
        if name.lower() == 'array':
            name = 'any[]'
        if name.lower() == 'map':
            name = 'Map<any, any>'
        if name.lower() == 'promise':
            name = 'Promise<any>'
        if name.lower() == 'iterator':
            name = 'Iterator<any>'
        if name == '*':
            name = 'any'
        if name.startswith("Array.<"):  # this is really bad!
            # this can only happen if we are combined with a different type, and the ui5 api json
            # sadly splits this multi-type-array at this inner "|"
            # see: Input::getSuggestionRows
            name = "Array<" + name[len("Array.<"):]
        if name.startswith("Promise.<"):
            name = "Promise<" + name[len("Promise.<"):]
        name = OBJ_MAP.sub(r'Map<\1,\2>', name)
        name = name.replace("function()", "Function")
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

    def trim_by(self, base_uri: str):
        if self.name.startswith('{'):
            return
        base_parts = base_uri.split('.')
        self_parts = self.name.split('.')
        if self_parts[0] != base_parts[0] and len(self_parts) > 1:
            self.name = 'globalThis.' + self.name
            return
        # actually shortining the type intoduces more ambiguity errors
        # while len(base_parts) > 0 and len(self_parts) > 1 and base_parts[0] == self_parts[0]:
        #     base_parts.pop(0)
        #     self_parts.pop(0)
        # self.name = '.'.join(self_parts)

    def written(self) -> str:
        return self.name

    def contains_plain_object(self):
        return self.written() == 'object'

    def replace_plain_object_with(self, fancy_object: 'TsType') -> 'TsType':
        return fancy_object


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

    def trim_by(self, base_uri: str):
        for option in self.options:
            option.trim_by(base_uri)

    def written(self) -> str:
        return '(' + " | ".join([o.written() for o in self.options]) + ")"

    def contains_plain_object(self):
        return any([option.written() == 'object' for option in self.options])

    def replace_plain_object_with(self, fancy_object: 'TsType') -> 'TsType':
        for i, option in enumerate(self.options):
            if option.contains_plain_object():
                self.options[i] = option.replace_plain_object_with(fancy_object)
                return self
        raise Exception("I do not contain a plain Object!")
