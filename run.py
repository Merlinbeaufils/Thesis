import os
from argparse import Namespace, ArgumentParser
from typing import Tuple, List

import torch
from pytorch_lightning import Trainer
from pytorch_lightning.loggers import TensorBoardLogger
from torch.utils.data import DataLoader, random_split

from project.dataloading import BaseTreeDataset, ContTreeDataset
from project.frequency import build_trees, build_vocabularies, build_files, Vocabulary
from project.model_pipe import BaseModel
from project.models.flat_bow import FlatEmbedding, SimpleLinear, FlatEmbeddingAndLinear
from project.parsing import pickle_dump, pickle_load, HtmlNode
from project.sparsing import random_sparse, sparse_depth
from project.tree_tokenizer import BaseTokenizer

torch.manual_seed(1)

file_loc = './data/'

#models_loc = './project/models/'  # models


def reduce_trees(reduction: str, trees: List[HtmlNode], args: Namespace) -> None:
    if reduction == 'random':
        function = random_sparse
        goal_size = args.goal_size
    elif reduction == 'depth':
        function = sparse_depth
        goal_size = args.max_depth
    else:
        raise NoReduction
    for tree in trees:
        function(tree, goal_size)
    pickle_dump(directory=args.setup_location + 'trees/trees_short', item=trees)
    args.reduction_function = function


def set_models(model_type: str, vocab, dataset, embedding_dim=600, learning_rate=1e-4):
    num_embeddings = len(vocab) + 40
    # if model_type == 'lin':
    #     submodel = SimpleLinear(in_features=num_embeddings, out_features=embedding_dim)
    # elif model_type == 'flatlin':
    #     submodel = FlatEmbeddingAndLinear(num_embeddings=num_embeddings, embedding_dim=embedding_dim)
    if model_type == 'flat':
        submodel = FlatEmbedding(num_embeddings=num_embeddings, embedding_dim=embedding_dim)
        #submodel = FlatSum()
    else:
        raise NoModel
    model = BaseModel(dataset=dataset, tree_model=submodel, lr=learning_rate)
    return model, submodel


def set_dataloader(dataloader: str, trees: List[HtmlNode], indexes_size: int,
                   train_proportion: int, args: Namespace) -> Tuple[
    DataLoader, DataLoader, BaseTreeDataset]:
    vocabs = [args.total] if args.total_vocab else [args.tags, args.keys, args.values]
    if dataloader == 'base':
        dataset = BaseTreeDataset(trees=trees, indexes_length=indexes_size,
                                  total=True, key_only=True, vocabs=vocabs)
        train_size = int(train_proportion * len(dataset))
        test_size = len(dataset) - train_size
        train_data, test_data = random_split(dataset, [train_size, test_size])
    elif dataloader == 'Cont':
        dataset = ContTreeDataset(trees=trees, indexes_length=indexes_size,
                                  total=True, key_only=True, vocabs=vocabs)
        train_size = int(train_proportion * len(dataset))
        test_size = len(dataset) - train_size
        train_data, test_data = random_split(dataset, [train_size, test_size])
    else:
        raise NoDataloader
    train_dataloader, test_dataloader = DataLoader(train_data, batch_size=64, shuffle=True), \
                                        DataLoader(test_data, batch_size=64, shuffle=True)
    os.makedirs(args.setup_location + 'dataloaders', mode=0o777, exist_ok=True)
    pickle_dump(args.setup_location + 'dataloaders/train_' + dataloader, train_dataloader)
    pickle_dump(args.setup_location + 'dataloaders/test_' + dataloader, test_dataloader)
    pickle_dump(args.setup_location + 'dataloaders/dataset_' + dataloader, dataset)
    return train_dataloader, test_dataloader, dataset


def main(args: Namespace) -> None:
    args.setup_location = file_loc + args.folder_name + '/'
    setup_location = args.setup_location
    if args.skip_setup:
        args.trees = pickle_load(directory=setup_location + 'trees/trees_short')
        args.tags = pickle_load(directory=setup_location + 'vocabs/tags')
        args.keys = pickle_load(directory=setup_location + 'vocabs/keys')
        args.values = pickle_load(directory=setup_location + 'vocabs/values')
        args.total = pickle_load(directory=setup_location + 'vocabs/total')
        train_dataloader = pickle_load(directory=setup_location + 'dataloaders/train_' + args.dataloader)
        test_dataloader = pickle_load(directory=setup_location + 'dataloaders/test_' + args.dataloader)
        dataset = pickle_load(directory=setup_location + 'dataloaders/dataset_' + args.dataloader)
    else:
        if args.build_trees:
            args.trees = build_trees(directory=setup_location, Pickle_trees=args.pickle_trees)
        else:
            args.trees = pickle_load(directory=setup_location + 'trees/trees')

        if args.build_vocabs:
            build_files(setup_location, setup_location + 'text_files', key_only=args.key_only)
            args.tags, args.keys, args.values, args.total = \
                build_vocabularies(directory=setup_location, total_floor=args.total_floor)
        else:
            args.tags = pickle_load(directory=setup_location + 'vocabs/tags')
            args.keys = pickle_load(directory=setup_location + 'vocabs/keys')
            args.values = pickle_load(directory=setup_location + 'vocabs/values')
            args.total = pickle_load(directory=setup_location + 'vocabs/total')

        reduce_trees(args.reduction, args.trees, args)

        if args.stop:
            raise Stop

        train_dataloader, test_dataloader, dataset = set_dataloader(dataloader=args.dataloader, trees=args.trees,
                                                                    indexes_size=args.indexes_size,
                                                                    train_proportion=args.train_proportion, args=args)


    train_features, train_labels = next(iter(train_dataloader))
    test_features, test_labels = next(iter(train_dataloader))
    feature, label = train_features[0], train_labels[0]

    basemodel = BaseModel(dataset=dataset, tree_model_type=args.tree_model_type, vocab_size=len(args.total),
                          node_model_type=args.node_model_type, optimizer_type=args.optimizer, batch_size=args.batch_size,
                          lr=args.lr, loss_type=args.loss, similarity_type=args.similarity,
                          train_proportion=args.train_proportion)

    # basemodel, submodel = set_models(model_type=args.model_type,
    #                                  vocab=args.total, dataset=dataset, learning_rate=args.lr)
    logger = TensorBoardLogger('tb_logs', name=args.node_model_type)
    trainer = Trainer(
        gpus=0,
        logger=[logger],
        max_epochs=5
    )
    trainer.fit(basemodel)
    pass


def test_some_stuff():
    total_vocab: Vocabulary = pickle_load('./data/common_sites/vocabs/total')
    # train_dataloader = pickle_load('./data/common_sites/dataloaders/train_base')
    trees = pickle_load('./data/common_sites/trees/trees')
    indexes_size = 100
    vocabs = [total_vocab]
    dataset = BaseTreeDataset(trees=trees, indexes_length=indexes_size,
                              total=True, key_only=True, vocabs=vocabs)
    # dataset = pickle_load('./data/common_sites/dataloaders/dataset_base')
    train_dataloader = DataLoader(dataset, 1, True)
    features, labels = next(iter(train_dataloader))
    feature, label = features[0], labels[0]
    tokenizer = BaseTokenizer(vocabs=[total_vocab], total=True)
    node = tokenizer.back_to_node(feature)
    tree = tokenizer.back_to_tree(label)
    print('hi')


if __name__ == "__main__":
    parser = ArgumentParser(description='Process specifications')
    parser.add_argument('--pickle_trees', action='store_true')
    parser.add_argument('--folder_name', type=str, default='common_sites')
    parser.add_argument('--reduction', type=str, default='random')
    parser.add_argument('--build_vocabs', action='store_true')
    parser.add_argument('--include_data', action='store_true')
    parser.add_argument('--build_trees', action='store_true')
    parser.add_argument('--total_file_setup', action='store_true')
    parser.add_argument('--sampling', type=str, default='all')
    parser.add_argument('--indexes_size', type=int, default=10_000)
    parser.add_argument('--train_length', type=int, default=400)
    parser.add_argument('--test_length', type=int, default=100)
    parser.add_argument('--train_proportion', type=float, default=0.8)
    parser.add_argument('--max_tree_size', type=int, default=500)
    parser.add_argument('--pad_value', type=int, default=0)  # pad_value currently equal to 'other' values
    parser.add_argument('--tag_other', type=int, default=0)
    parser.add_argument('--key_other', type=int, default=0)
    parser.add_argument('--value_other', type=int, default=0)
    parser.add_argument('--skip_setup', action='store_true')
    parser.add_argument('--tree_model_type', type=str, default=None)
    parser.add_argument('--node_model_type', type=str, default='flat')
    parser.add_argument('--dataloader', type=str, default='base')
    parser.add_argument('--total_floor', type=int, default=2)
    parser.add_argument('--key_only', action='store_true')
    parser.add_argument('--total_vocab', action='store_true')
    parser.add_argument('--optimizer', type=str, default='sgd')
    parser.add_argument('--loss', type=str, default='cross_entropy')
    parser.add_argument('--similarity', type=str, default='cosine')
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--max_depth', type=int, default=10)
    parser.add_argument('--goal_size', type=int, default=500)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--test', action='store_true')

    names: Namespace = parser.parse_args()
    names.total_vocab = True  # change this at some point
    if names.test:
        test_some_stuff()
    main(names)


class NoIndex(Exception):
    pass


class NoReduction(Exception):
    pass


class NoModel(Exception):
    pass


class NoDataloader(Exception):
    pass


class Stop(Exception):
    pass


