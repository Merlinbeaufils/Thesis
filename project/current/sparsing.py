import random

from project.current.parsing import HtmlNode


def random_sparse(tree: HtmlNode, goal_size): # reduce number of nodes in tree to at most goal_size
    while len(tree.path) > goal_size:
        target_node = tree.path[random.randint(0, len(tree.path) - 2)]
        target_node.father.children = [child for child in target_node.father.children if child != target_node]
        tree.build_path()
    return tree


