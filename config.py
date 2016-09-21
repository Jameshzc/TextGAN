import collections

import tensorflow as tf

flags = tf.flags

# command-line config
flags.DEFINE_string("data_path",  "data",            "Data path")
flags.DEFINE_string("vocab_file", "models/vocab.pk", "Vocab pickle file")


class Config(object):
    def __init__(self):
        # copy flag values to attributes of this Config object
        for k, v in sorted(flags.FLAGS.__dict__['__flags'].items(), key=lambda x: x[0]):
            setattr(self, k, v)

