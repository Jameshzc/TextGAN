from __future__ import division

import cPickle as pickle
import glob
from os.path import join as pjoin
import random

import nltk
import numpy as np
import tensorflow as tf

from config import cfg
import utils


class Vocab(object):

    '''Stores the vocab: forward and reverse mappings'''

    def __init__(self):
        self.vocab = ['<pad>', '<sos>', '<eos>', '<unk>']
        self.vocab_lookup = {w: i for i, w in enumerate(self.vocab)}
        self.sos_index = self.vocab_lookup.get('<sos>')
        self.eos_index = self.vocab_lookup.get('<eos>')
        self.unk_index = self.vocab_lookup.get('<unk>')

    def load_by_parsing(self, save=False, verbose=True):
        '''Read the vocab from the dataset'''
        if verbose:
            print 'Loading vocabulary by parsing...'
        fnames = glob.glob(pjoin(cfg.data_path, '*.txt'))
        for fname in fnames:
            if verbose:
                print fname
            with open(fname, 'r') as f:
                for line in f:
                    for word in utils.read_words(line, chars=cfg.char_model):
                        if word not in self.vocab_lookup:
                            self.vocab_lookup[word] = len(self.vocab)
                            self.vocab.append(word)
        if verbose:
            print 'Vocabulary loaded, size:', len(self.vocab)

    def load_from_pickle(self, verbose=True):
        '''Read the vocab from a pickled file'''
        if cfg.char_model:
            pkfile = cfg.char_vocab_file
        else:
            pkfile = cfg.word_vocab_file
        try:
            if verbose:
                print 'Loading vocabulary from pickle...'
            with open(pkfile, 'rb') as f:
                self.vocab, self.vocab_lookup = pickle.load(f)
            if verbose:
                print 'Vocabulary loaded, size:', len(self.vocab)
        except IOError:
            if verbose:
                print 'Error loading from pickle, attempting parsing.'
            self.load_by_parsing(save=True, verbose=verbose)
            with open(pkfile, 'wb') as f:
                pickle.dump([self.vocab, self.vocab_lookup], f, -1)
                if verbose:
                    print 'Saved pickle file.'

    def lookup(self, words):
        return [self.sos_index] + [self.vocab_lookup.get(w) for w in words] + [self.eos_index]


class Reader(object):

    def __init__(self, vocab):
        self.vocab = vocab
        random.seed(0)  # deterministic random

    def read_lines(self, fnames):
        '''Read single lines from data'''
        for fname in fnames:
            with open(fname, 'r') as f:
                for line in f:
                    yield self.vocab.lookup([w for w in utils.read_words(line,
                                                                         chars=cfg.char_model)])

    def buffered_read_sorted_lines(self, fnames, batches=50):
        '''Read and return a list of lines (length multiple of batch_size) worth at most $batches
           number of batches sorted in length'''
        buffer_size = cfg.batch_size * batches
        lines = []
        for line in self.read_lines(fnames):
            lines.append(line)
            if len(lines) == buffer_size:
                lines.sort(key=lambda x: len(x))
                yield lines
                lines = []
        if lines:
            lines.sort(key=lambda x: len(x))
            mod = len(lines) % cfg.batch_size
            if mod != 0:
                lines = [[self.vocab.sos_index, self.vocab.eos_index]
                         for _ in xrange(cfg.batch_size - mod)] + lines
            yield lines

    def buffered_read(self, fnames):
        '''Read packed batches from data with each batch having lines of similar lengths'''
        for line_collection in self.buffered_read_sorted_lines(fnames):
            batches = [b for b in utils.grouper(cfg.batch_size, line_collection)]
            random.shuffle(batches)
            for batch in batches:
                yield self.pack(batch)

    def training(self):
        '''Read batches from training data'''
        for batch in self.buffered_read([pjoin(cfg.data_path, 'train.txt')]):
            yield batch

    def validation(self):
        '''Read batches from validation data'''
        for batch in self.buffered_read([pjoin(cfg.data_path, 'valid.txt')]):
            yield batch

    def testing(self):
        '''Read batches from testing data'''
        for batch in self.buffered_read([pjoin(cfg.data_path, 'test.txt')]):
            yield batch

    def _word_dropout(self, sent):
        ret = []
        if cfg.char_model:
            space = self.vocab.vocab_lookup[' ']
            keep = 1  # the number of characters to skip for dropout consideration
        for word in sent:
            if cfg.char_model:
                if word == space:
                    keep = 2  # don't drop space and the first character of the next word
                else:
                    keep -= 1
            if keep <= 0 and random.random() < cfg.word_dropout:
                ret.append(self.vocab.unk_index)
            else:
                ret.append(word)
        return ret

    def pack(self, batch):
        '''Pack python-list batches into numpy batches'''
        max_size = max(len(s) for s in batch)
        if len(batch) < cfg.batch_size:
            batch.extend([[] for _ in xrange(cfg.batch_size - len(batch))])
        leftalign_batch = np.zeros([cfg.batch_size, max_size], dtype=np.int32)
        leftalign_drop_batch = np.zeros([cfg.batch_size, max_size], dtype=np.int32)
        sent_lengths = np.zeros([cfg.batch_size], dtype=np.int32)
        for i, s in enumerate(batch):
            leftalign_batch[i, :len(s)] = s
            leftalign_drop_batch[i, :len(s)] = [s[0]] + self._word_dropout(s[1:-1]) + [s[-1]]
            sent_lengths[i] = len(s)
        return (leftalign_batch, leftalign_drop_batch, sent_lengths)


def main(_):
    '''Reader tests'''

    vocab = Vocab()
    vocab.load_from_pickle()

    reader = Reader(vocab)
    for batch in reader.training():
        for line in batch[0]:
            print line
            for e in line:
                print vocab.vocab[e],
            print
            print


if __name__ == '__main__':
    tf.app.run()
