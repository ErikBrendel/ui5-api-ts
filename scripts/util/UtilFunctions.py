forbidden_words = ['with', 'as']
forbidden_chars = [' ', ':', '/', '-', '<', '>', '{', '}', '[', ']']


def visibility_parse(raw_visibility: str) -> str:
    if raw_visibility == 'restricted':
        return 'private'
    return raw_visibility


def pp_type(name: str) -> str:
    """pretty-print a type or identifier (e.g. allowing array brackets and templates)"""
    name = name.strip()
    if name in forbidden_words:
        return '_' + name
    if 'module:' in name:
        name = name.replace('module:', '').replace('/', '.')
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
    name = name.replace("function", "_function")
    return name


def capitalize_first(data: str) -> str:
    return data[0].capitalize() + data[1:]
