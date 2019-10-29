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
        name = pp_type(name)
        if name == 'function':
            name = 'Function'
        if name == 'int':
            name = 'number'
        if name == 'int[]':
            name = 'number[]'
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
        if name == 'array':
            name = 'any[]'
        if name == 'map':
            name = 'any'
        if name == '*':
            name = 'any'
        if name.startswith("Array.<") and not name.endswith(">"):  # this is really bad!
            # this can only happen if we are combined with a different type, and the ui5 api json
            # sadly splits this multi-type-array at this inner "|"
            # see: Input::getSuggestionRows
            name = "Array<" + name[len("Array.<"):]
        if name.startswith("Promise.<") and name.endswith(">"):
            name = "Promise<" + name[len("Promise.<"):]
        name = OBJ_MAP.sub(r'Map<\1,\2>', name)
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