from argparse import ArgumentParser
import os
from typing import Generator
from tree_sitter import Node, Parser, Language, Tree
import tree_sitter_cpp as cpp

args_parser = ArgumentParser()
args_parser.add_argument("f", type=str)
args = args_parser.parse_args()
file = os.path.splitext(str(args.f))[0]

with open(file + ".h", "r") as f:
    code_header = f.read()

parser = Parser()
parser.set_language(Language(cpp.language(), "cpp"))
tree = parser.parse(bytes(code_header, "utf8"))


def traverse_node(tree: Node) -> Generator[Node, None, None]:
    cursor = tree.walk()

    visited_children = False
    while True:
        if not visited_children:
            yield cursor.node
            if not cursor.goto_first_child():
                visited_children = True
        elif cursor.goto_next_sibling():
            visited_children = False
        elif not cursor.goto_parent():
            break


class MethodDefine:
    def __init__(
        self, id: str, args: list[str], defvals: list[str], is_static=False, cls_name=""
    ):
        self.id = id
        self.args = args
        self.defvals = defvals
        self.is_static = is_static
        self.cls_name = cls_name


fn_list: list[MethodDefine] = []

for cls_node in [
    x for x in traverse_node(tree.root_node) if x.type == "class_specifier"
]:
    cls_name = str(cls_node.child(1).text, "utf8")
    field_decl = [x for x in cls_node.children if x.type == "field_declaration_list"]
    assert len(field_decl) > 0
    field_decl = field_decl[0]
    cursor = field_decl.walk()
    cursor.goto_first_child()
    start_public = False
    skip_one = False
    while cursor.goto_next_sibling():
        node = cursor.node
        if node.type == "access_specifier":
            start_public = node.text == b"public"
        if (
            start_public
            and node.type == "comment"
            and str(node.text, "utf8").replace(" ", "") == "/*gd_ignore*/"
        ):
            skip_one = True
        if start_public and (
            node.type == "field_declaration" or node.type == "function_definition"
        ):
            if skip_one:
                skip_one = False
                continue
            is_static = (
                node.child(0).type == "storage_class_specifier"
                and node.child(0).text == b"static"
            )
            fn_decl = [x for x in node.children if x.type == "function_declarator"]
            if len(fn_decl) == 0:
                continue
            else:
                fn_decl = fn_decl[0]
            id = str(fn_decl.child(0).text, "utf8")
            parameters_node: Node = fn_decl.child(1)
            parameters = [
                x
                for x in parameters_node.children
                if x.type == "parameter_declaration"
                or x.type == "optional_parameter_declaration"
            ]
            args = [
                str(
                    [a for a in traverse_node(p) if a.type == "identifier"][0].text,
                    "utf8",
                )
                for p in parameters
            ]
            if (id == cls_name or id == "~" + cls_name) and len(args) == 0:
                continue
            defvals = [
                str(p.child(3).text, "utf8")
                for p in parameters
                if p.type == "optional_parameter_declaration"
            ]
            fn_list.append(MethodDefine(id, args, defvals, is_static, cls_name))

for fn in fn_list:
    if fn.is_static:
        print(
            f"""ClassDB::bind_static_method("{fn.cls_name}", D_METHOD("{fn.id}"{'' if len(fn.args)==0 else ','+','.join(['"'+a+'"' for a in fn.args])}), &{fn.cls_name}::{fn.id}{'' if len(fn.defvals)==0 else ','+','.join(["DEFVAL("+v+")" for v in fn.defvals])});"""
        )
    else:
        print(
            f"""ClassDB::bind_method(D_METHOD("{fn.id}"{'' if len(fn.args)==0 else ','+','.join(['"'+a+'"' for a in fn.args])}), &{fn.cls_name}::{fn.id}{'' if len(fn.defvals)==0 else ','+','.join(["DEFVAL("+v+")" for v in fn.defvals])});"""
        )
