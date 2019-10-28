import re
from bs4 import BeautifulSoup


orig_prettify = BeautifulSoup.prettify
r = re.compile(r'^(\s*)', re.MULTILINE)
def prettify(self, encoding=None, formatter="minimal", indent_width=4):
    return r.sub(r'\1' * indent_width, orig_prettify(self, encoding, formatter))
BeautifulSoup.prettify = prettify


CROSS_LINK = re.compile(r"<a[^>]* href=\"#/api/([a-zA-Z0-9.]+)\"[^>]*>\1</a>")


class Comment:
    text: str
    uri: str

    def __init__(self, text: str, uri: str = None):
        self.text = text
        self.uri = uri

    def write(self, f: 'TextIO', indent: str):
        if self.text is None or len(self.text) == 0:
            return
        pretty_text = self.pretty_print(self.clean_text())
        if self.uri is not None:
            pretty_text += '\nOpen <a href="https://sapui5.netweaver.ondemand.com/#/api/' + self.uri + '">the docs</a>'
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
