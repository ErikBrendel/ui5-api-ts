forbidden_words = ['export', 'with', 'as']
forbidden_chars = [' ', ':', '/', '-', '<', '>', '{', '}', '[', ']']


def pp(name: str) -> str:
    """pretty-print a type or identifier"""
    if name in forbidden_words:
        return '_' + name
    if name.startswith('module:'):
        name = name[len('module:'):].replace('/', '.')
    for char in forbidden_chars:
        name = name.replace(char, '_')
    return name


def ppn(name: str) -> str:
    """pretty-print a variable name"""
    name = pp(name)
    name = name.replace(".", "_")
    return name


def capitalize_first(data: str) -> str:
    return data[0].capitalize() + data[1:]
