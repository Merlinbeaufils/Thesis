# from typing import List, Tuple
import random
from typing import Tuple, List
from argparse import Namespace

from torch import Tensor
from torch.utils.data import DataLoader
from torch.utils.data import Dataset

from project.current.parsing import pickle_load, pickle_dump
from project.current.sparsing import random_sparse
from project.current.tree_tokenizer import Node_Tokens, Tree_Tokens, tokenize_node, tokenize_tree
from project.current.parsing import HtmlNode



Tuple_list = List[Tuple[int, int]]
Sample = Tuple[Node_Tokens, Tree_Tokens]
Samples = List[Sample]
Forest = List[HtmlNode]
Tensorized_Sample = Tuple[Tensor, Tensor]
Tensorized_Samples = List[Tensorized_Sample]
PAD_VALUE = 0


def total_build_indexes(trees: List[HtmlNode], size: int = 200) -> Tuple_list:
    # Builds extensive indexes of every tree-subtree pair
    indexes = []
    for tree_index in range(len(trees)):
        for tree_path_index in range(len(trees[tree_index].path)):
            indexes.append((tree_path_index, tree_index))
    random.shuffle(indexes)
    print('done with indexes. Length: ', len(indexes))
    return indexes[:size]


class CustomTreeDataset(Dataset):  # Tree dataset class allowing handling of html trees
    def __init__(self, indexes: Tuple_list, tree_directory: str, args: Namespace):
        # indexes is a list of (tree_path_index, tree_index) tuples indicating (node, tree, pair)
        super().__init__()
        self.indexes = indexes
        self.trees:   Forest = pickle_load(tree_directory)
        self.samples: Samples = []
        self.tree_max: int = 0
        self.node_max: int = 0
        self.my_collate = 0
        self.build_samples(indexes, args)
        if not self.my_collate:
            self.padding_tokens()

    def __getitem__(self, index: int) -> Tensorized_Sample:  # returns a (subtree, tree) pair. Tokenized
        token_node, token_tree = self.samples[index]
        return Tensor(token_node), Tensor(token_tree)

    def __len__(self) -> int:  # returns # of samples
        return len(self.indexes)

    def build_samples(self, indexes: Tuple_list, args: Namespace) -> None:
        # Creates a list of (tokenized subtree, tokenized tree) pairs
        self.samples.clear()
        i = 0  # for debug purposes
        for tree_index_path, tree_index in indexes:
            i += 1
            tree: HtmlNode = self.trees[tree_index]
            node: HtmlNode = tree.path[tree_index_path]
            tokenized_node = tokenize_node(node, args)
            node.mask_self()
            tokenized_tree = tokenize_tree(tree, args)
            node.unmask_self()
            tree_node_max = len(max(tokenized_tree, default=0, key=len))
            if not self.my_collate:
                node_len = max(tree_node_max, len(tokenized_node))
                if node_len > self.node_max:
                    self.node_max = node_len
                tree_len = len(tokenized_tree)
                if tree_len > self.tree_max:
                    self.tree_max = tree_len
            self.samples.append((tokenized_node, tokenized_tree))


    def padding_tokens(self) -> None:
        for node_sample, tree_sample in self.samples:
            pad_node(node_sample, self.node_max)
            pad_tree(tree_sample, self.tree_max, self.node_max)

    def reduce_trees(self, max_size=500):
        for tree in self.trees:
            random_sparse(tree, max_size)


class MlmTreeDataset(CustomTreeDataset):
    def __init__(self, indexes: Tuple_list, tree_directory: str, args: Namespace, tokenizer):
        super().__init__(indexes=indexes, tree_directory=tree_directory, args=args)
        self.node_tokenizer = tokenizer

    def build_samples(self, indexes: Tuple_list, args: Namespace):
        self.samples.clear()
        i = 0
        for tree_index_path, tree_index in indexes:
            i += 1
            node: HtmlNode = self.trees[tree_index].path[tree_index_path]
            tree: HtmlNode = self.trees[tree_index]
            tokenized_node = self.tokenizer(node, args)
            node.mask_self()
            tokenized_tree = tokenize_tree(tree, args, self.tokenizer)
            node.unmask_self()
            tree_node_max = len(max(tokenized_tree, default=0, key=len))
            if not self.my_collate:
                node_len = max(tree_node_max, len(tokenized_node))
                if node_len > self.node_max:
                    self.node_max = node_len
                tree_len = len(tokenized_tree)
                if tree_len > self.tree_max:
                    self.tree_max = tree_len
            self.samples.append((tokenized_node, tokenized_tree))


def pad_tree(tree: list, length_tree: int, length_node: int) -> None:
    for node in tree:
        pad_node(node, length_node)
    while len(tree) < length_tree:
        tree.append([PAD_VALUE] * length_node)
    if len(tree) > length_tree:
        raise PadError


def pad_node(node: list, length_node: int) -> None:
    while len(node) < length_node:
        node.append(PAD_VALUE)
    if len(node) > length_node:
        raise PadError


def basic_data_loader_build(args: Namespace, size: int = 500) -> (DataLoader, DataLoader):
    indexes = total_build_indexes(size)
    train_length = int(0.8 * len(indexes))
    # test_length = len(indexes) - train_length
    training_data = CustomTreeDataset(indexes[:train_length], './data/common_sites/trees/trees_short', args)
    test_data = CustomTreeDataset(indexes[train_length:], './data/common_sites/trees/trees_short', args)
    train_dataloader = DataLoader(training_data, batch_size=64, shuffle=True)
    test_dataloader = DataLoader(test_data, batch_size=64, shuffle=True)
    return train_dataloader, test_dataloader


# dataset = CustomTreeDataset(indexes, './tree_directory')
def collate_function(batch: Samples):
    node_max, tree_max = 0, 0
    new_batch = []
    for node, tree in batch:
        tree_node_max = len(max(tree, default=0, key=len))
        node_len = max(tree_node_max, len(node))
        tree_len = len(tree)
        if node_len > node_max:
            node_max = node_len
        if tree_len > tree_max:
            tree_max = tree_len
    for node, tree in batch:
        pad_node(node, node_max)
        pad_tree(tree, tree_max, node_max)
        node_tensor = Tensor(node)
        tree_tensor = Tensor(node)
        new_batch.append((node_tensor, tree_tensor))
    return new_batch


class PadError(Exception):
    pass