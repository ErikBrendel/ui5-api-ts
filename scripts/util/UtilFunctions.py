forbidden_words = ['export', 'with', 'as']
forbidden_chars = [' ', ':', '/', '-', '<', '>', '{', '}', '[', ']']


def pp_type(name: str) -> str:
    """pretty-print a type or identifier (e.g. allowing array brackets and templates)"""
    if name in forbidden_words:
        return '_' + name
    if name.startswith('module:'):
        name = name[len('module:'):].replace('/', '.')
    return name


def pp_class_name(name: str) -> str:
    """pretty-print a name of a class or namespace"""
    name = pp_type(name)
    for char in forbidden_chars:
        name = name.replace(char, '_')
    return name


def pp_name(name: str) -> str:
    """pretty-print a variable name"""
    name = pp_class_name(name)
    name = name.replace(".", "_")
    return name


def capitalize_first(data: str) -> str:
    return data[0].capitalize() + data[1:]
