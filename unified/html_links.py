"""Rewrite URL attributes structurally; preserve embedded charts/scripts verbatim."""
from html import escape
from html.parser import HTMLParser


class ModuleHTML(HTMLParser):
    def __init__(self, system_id):
        super().__init__(convert_charrefs=False)
        self.system_id = system_id
        self.parts = []

    def start_tag(self, tag, attrs, suffix):
        from .urls import local_url
        attributes = []
        for key, value in attrs:
            if value is not None and key in {"href", "src", "action", "poster", "data-api"}:
                value = local_url(value, self.system_id)
            attributes.append(key if value is None else key + '="' + escape(value, quote=True) + '"')
        self.parts.append("<" + tag + (" " + " ".join(attributes) if attributes else "") + suffix)

    def handle_starttag(self, tag, attrs):
        self.start_tag(tag, attrs, ">")

    def handle_startendtag(self, tag, attrs):
        self.start_tag(tag, attrs, "/>")

    def handle_endtag(self, tag):
        if tag == "head" and self.system_id == "test":
            self.parts.append('<link rel="stylesheet" href="/test-channel.css?v=20261110">')
        self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append("&" + name + ";")

    def handle_charref(self, name):
        self.parts.append("&#" + name + ";")

    def handle_comment(self, data):
        self.parts.append("<!--" + data + "-->")

    def handle_decl(self, decl):
        self.parts.append("<!" + decl + ">")


def rewrite_html(text, system_id):
    parser = ModuleHTML(system_id)
    parser.feed(text)
    parser.close()
    return "".join(parser.parts).encode("utf-8")
