from __future__ import division

import cPickle as pickle
import glob
from os.path import join as pjoin
import random

import nltk
import numpy as np
import tensorflow as tf

from config import Config
import utils


class Vocab(object):
    '''Stores the vocab: forward and reverse mappings'''
    def __init__(self, config):
        self.config = config
        self.vocab = ['<pad>', '<sos>', '<eos>', '<unk>']
        self.vocab_lookup = {w:i for i,w in enumerate(self.vocab)}
        self.unk_index = self.vocab_lookup.get('<unk>')
        self.sos_index = self.vocab_lookup.get('<sos>')
        self.eos_index = self.vocab_lookup.get('<eos>')


    def load_by_parsing(self, save=False, verbose=True):
        '''Read the vocab from the dataset'''
        if verbose:
            print 'Loading vocabulary by parsing...'
        fnames = glob.glob(pjoin(self.config.data_path, '*.txt'))
        for fname in fnames:
            if verbose:
                print fname
            with open(fname, 'r') as f:
                for line in f:
                    for word in utils.read_words(line):
                        if word not in self.vocab_lookup:
                            self.vocab_lookup[word] = len(self.vocab)
                            self.vocab.append(word)
        if verbose:
            print 'Vocabulary loaded, size:', len(self.vocab)

    def load_from_pickle(self, verbose=True):
        '''Read the vocab from a pickled file'''
        pkfile = self.config.vocab_file
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
        return [self.sos_index] + [self.vocab_lookup.get(w, self.unk_index) for w in words] + \
               [self.eos_index]


class Reader(object):
    def __init__(self, config, vocab):
        self.config = config
        self.vocab = vocab
        random.seed(0) # deterministic random

    def read_lines(self, fnames):
        '''Read single lines from data'''
        for fname in fnames:
            with open(fname, 'r') as f:
                for line in f:
                    yield self.vocab.lookup([w for w in utils.read_words(line)])

    def buffered_read_sorted_lines(self, fnames, batches=50):
        '''Read and return a list of lines (length multiple of batch_size) worth at most $batches
           number of batches sorted in length'''
        buffer_size = self.config.batch_size * batches
        lines = []
        for line in self.read_lines(fnames):
            lines.append(line)
            if len(lines) == buffer_size:
                lines.sort(key=lambda x:len(x))
                yield lines
                lines = []
        if lines:
            lines.sort(key=lambda x:len(x))
            mod = len(lines) % self.config.batch_size
            if mod != 0:
                lines = [[self.vocab.sos_index, self.vocab.eos_index]
                         for _ in xrange(self.config.batch_size - mod)] + lines
            yield lines

    def buffered_read(self, fnames):
        '''Read packed batches from data with each batch having lines of similar lengths'''
        for line_collection in self.buffered_read_sorted_lines(fnames):
            batches = [b for b in utils.grouper(self.config.batch_size, line_collection)]
            random.shuffle(batches)
            for batch in batches:
                yield self.pack(batch)

    def training(self):
        '''Read batches from training data'''
        for batch in self.buffered_read([pjoin(self.config.data_path, 'train.txt')]):
            yield batch

    def validation(self):
        '''Read batches from validation data'''
        for batch in self.buffered_read([pjoin(self.config.data_path, 'valid.txt')]):
            yield batch

    def testing(self):
        '''Read batches from testing data'''
        for batch in self.buffered_read([pjoin(self.config.data_path, 'test.txt')]):
            yield batch

    def _word_dropout(self, sent):
        ret = []
        for word in sent:
            if random.random() < self.config.word_dropout:
                ret.append(self.vocab.unk_index)
            else:
                ret.append(word)
        return ret

    def pack(self, batch):
        '''Pack python-list batches into numpy batches'''
        max_size = max(len(s) for s in batch)
        if len(batch) < self.config.batch_size:
            batch.extend([[] for _ in xrange(self.config.batch_size - len(batch))])
        leftalign_batch = np.zeros([self.config.batch_size, max_size], dtype=np.int32)
        rightalign_batch = np.zeros([self.config.batch_size, max_size], dtype=np.int32)
        leftalign_drop_batch = np.zeros([self.config.batch_size, max_size], dtype=np.int32)
        rightalign_drop_batch = np.zeros([self.config.batch_size, max_size], dtype=np.int32)
        sent_lengths = np.zeros([self.config.batch_size], dtype=np.int32)
        for i, s in enumerate(batch):
            leftalign_batch[i, :len(s)] = s
            rightalign_batch[i, -len(s)+1:] = s[:-1] # no <eos>
            leftalign_drop_batch[i, :len(s)] = [s[0]] + self._word_dropout(s[1:-1]) + [s[-1]]
            rightalign_drop_batch[i, -len(s)+1:] = [s[0]] + self._word_dropout(s[1:-1]) # no <eos>
            sent_lengths[i] = len(s)
        return (leftalign_batch, rightalign_batch, leftalign_drop_batch, rightalign_drop_batch,
                sent_lengths)


def main(_):
    '''Reader tests'''
    config = Config()

    vocab = Vocab(config)
    vocab.load_from_pickle()

    reader = Reader(config, vocab)
    for batch in reader.training():
        for line in batch[0]:
            print line
            for e in line:
                print vocab.vocab[e],
            print
            print


if __name__ == '__main__':
    tf.app.run()
