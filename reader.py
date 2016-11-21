from pathlib import Path
import pickle
import random

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
            print('Loading vocabulary by parsing...')
        fnames = Path(cfg.data_path).glob('*.txt')
        for fname in fnames:
            if verbose:
                print(fname)
            with fname.open('r') as f:
                for line in f:
                    for word in utils.read_words(line, chars=cfg.char_model):
                        if word not in self.vocab_lookup:
                            self.vocab_lookup[word] = len(self.vocab)
                            self.vocab.append(word)
        if verbose:
            print('Vocabulary loaded, size:', len(self.vocab))

    def load_from_pickle(self, verbose=True):
        '''Read the vocab from a pickled file'''
        if cfg.char_model:
            pkfile = cfg.char_vocab_file
        else:
            pkfile = cfg.word_vocab_file
        try:
            if verbose:
                print('Loading vocabulary from pickle...')
            with open(pkfile, 'rb') as f:
                self.vocab, self.vocab_lookup = pickle.load(f)
            if verbose:
                print('Vocabulary loaded, size:', len(self.vocab))
        except IOError:
            if verbose:
                print('Error loading from pickle, attempting parsing.')
            self.load_by_parsing(save=True, verbose=verbose)
            with open(pkfile, 'wb') as f:
                pickle.dump([self.vocab, self.vocab_lookup], f, -1)
                if verbose:
                    print('Saved pickle file.')

    def lookup(self, words):
        return [self.sos_index] + [self.vocab_lookup.get(w) for w in words] + [self.eos_index]


class Reader(object):
    # TODO prepare non-overlapping datasets.

    def __init__(self, vocab):
        self.vocab = vocab
        random.seed(0)  # deterministic random

    def read_lines(self, fnames):
        '''Read single lines from data'''
        for fname in fnames:
            with fname.open('r') as f:
                for line in f:
                    yield self.vocab.lookup([w for w in utils.read_words(line,
                                                                         chars=cfg.char_model)])

    def buffered_read_sorted_lines(self, fnames, batches=50):
        '''Read and return a list of lines (length multiple of batch_size) worth at most $batches
           number of batches sorted in length'''
        # TODO allow not bucketing
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
                         for _ in range(cfg.batch_size - mod)] + lines
            yield lines

    def buffered_read(self, fnames):
        '''Read packed batches from data with each batch having lines of similar lengths'''
        for line_collection in self.buffered_read_sorted_lines(fnames):
            batches = [b for b in utils.grouper(cfg.batch_size, line_collection)]
            random.shuffle(batches)
            for batch in batches:
                ret = self.pack(batch)
                if ret is not None:
                    yield ret

    def training(self):
        '''Read batches from training data'''
        yield from self.buffered_read([Path(cfg.data_path) / 'train.txt'])

    def validation(self):
        '''Read batches from validation data'''
        yield from self.buffered_read([Path(cfg.data_path) / 'valid.txt'])

    def testing(self):
        '''Read batches from testing data'''
        yield from self.buffered_read([Path(cfg.data_path) / 'test.txt'])

    def pack(self, batch):
        '''Pack python-list batches into numpy batches'''
        max_size = max(len(s) for s in batch)
        if max_size > cfg.max_sent_length:
            return None
        if len(batch) < cfg.batch_size:
            batch.extend([[] for _ in range(cfg.batch_size - len(batch))])
        leftalign_batch = np.zeros([cfg.batch_size, cfg.max_sent_length], dtype=np.int32)
        sent_lengths = np.zeros([cfg.batch_size], dtype=np.int32)
        for i, s in enumerate(batch):
            leftalign_batch[i, :len(s)] = s
            sent_lengths[i] = len(s)
        return (leftalign_batch, sent_lengths)


def main(_):
    '''Reader tests'''

    vocab = Vocab()
    vocab.load_from_pickle()

    reader = Reader(vocab)
    for batch in reader.training():
        for line in batch[0]:
            print(line)
            for e in line:
                print(vocab.vocab[e], end=' ')
            print()
            print()


if __name__ == '__main__':
    tf.app.run()
